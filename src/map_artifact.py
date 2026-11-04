"""Versioned, data-only Parquet map snapshots (never pickle/executable data)."""
import ast
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
import re

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .storage_data import StorageClient, DataLoadError, StorageError

LOGGER = logging.getLogger('streamlit.prism.map_artifact')
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    LOGGER.addHandler(logging.StreamHandler())
LOGGER.propagate = False


class ArtifactVersionMismatch(ValueError):
    """Stored metadata does not match the requested data/calculation version."""


def function_source(source, names):
    """Hash source text, not ast.dump(), whose format changes across Python versions."""
    source = source.replace('\r\n', '\n').replace('\r', '\n')
    lines = source.splitlines(keepends=True)
    selected = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            start = min([node.lineno] + [item.lineno for item in node.decorator_list])
            selected.append(''.join(lines[start - 1:node.end_lineno]))
    return '\n'.join(selected).encode('utf-8')

SCHEMA_VERSION = 1
MAP_COLUMNS = ['_id', 'Name', 'Brand', 'Gender', 'Main Accords', 'Notes',
               'scent_map_x', 'scent_map_y', 'scent_map_angle', 'scent_map_radius',
               'scent_map_hue', 'scent_map_saturation', 'scent_map_lightness', 'plot_color']
REQUIRED_COLUMNS = set(MAP_COLUMNS) | {'tooltip', 'accord_values', 'note_lines',
                                     'marker_rgb', 'marker_border', 'marker_text'}


def logic_version(root):
    """Fingerprint actual calculation/preparation code, not an operator's guess."""
    root = Path(root)
    functions = {'hsl_to_css', 'marker_rgb', 'darker_border', 'contrast_text_color', 'prepare_view'}
    # Normalize platform line endings so Windows-built files work on Cloud/Linux.
    digest = hashlib.sha256((root/'src/scent_map.py').read_text(encoding='utf-8').encode())
    digest.update(function_source((root/'app.py').read_text(encoding='utf-8'), functions))
    digest.update(Path(__file__).read_text(encoding='utf-8').encode())
    return digest.hexdigest()[:16]


def artifact_filename(version, logic):
    readable = re.sub(r'[^A-Za-z0-9._-]+', '-', version).strip('-')[:100]
    suffix = hashlib.sha256(version.encode()).hexdigest()[:8]
    return f'scent-map-{readable}-{suffix}-logic-{logic}.parquet'


def write_artifact(path, view, section_angles, settings, logic, csv_sha256):
    if not REQUIRED_COLUMNS.issubset(view.columns):
        raise ValueError('Incomplete map artifact columns')
    metadata = {'schema': SCHEMA_VERSION, 'version': settings['version'], 'logic': logic,
                'source': settings['source'], 'object_path': settings.get('object_path', ''),
                'csv_sha256': csv_sha256, 'rows': len(view), 'section_angles': section_angles}
    table = pa.Table.from_pandas(view, preserve_index=False)
    table = table.replace_schema_metadata({**(table.schema.metadata or {}),
                                          b'prism': json.dumps(metadata, ensure_ascii=False).encode()})
    pq.write_table(table, path, compression='zstd')


def read_artifact(data, settings, logic):
    table = pq.read_table(BytesIO(data) if isinstance(data, bytes) else data)
    metadata = json.loads((table.schema.metadata or {})[b'prism'])
    expected = {'schema': SCHEMA_VERSION, 'version': settings['version'], 'logic': logic,
                'source': settings['source'], 'object_path': settings.get('object_path', '')}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ArtifactVersionMismatch('Map artifact version mismatch')
    if not REQUIRED_COLUMNS.issubset(table.column_names):
        raise ValueError('Incomplete map artifact')
    view = table.to_pandas()
    if len(view) != metadata['rows'] or view['_id'].duplicated().any():
        raise ValueError('Invalid map artifact rows')
    # Arrow lists become ndarrays in pandas; restore the original public shape.
    for name in ('accord_values', 'note_lines'):
        view[name] = view[name].map(list)
    return view, metadata['section_angles']


def fetch_artifact(settings, logic, root):
    name = artifact_filename(settings['version'], logic)
    if settings['source'] == 'local':
        return (Path(root)/'data/artifacts'/name).read_bytes()
    return StorageClient(settings['url'], settings['service_key'], settings['bucket'],
                         'map-artifacts/' + name).download()


def load_artifact_or_none(settings, logic, root):
    name = artifact_filename(settings['version'], logic)
    try:
        data = fetch_artifact(settings, logic, root)
    except (DataLoadError, OSError) as exc:
        missing = isinstance(exc, FileNotFoundError) or (isinstance(exc, StorageError) and exc.status == 404)
        reason = 'missing' if missing else 'download_error'
        LOGGER.warning('map artifact: fallback (reason=%s, file=%s, error=%s)', reason, name, type(exc).__name__)
        return None
    try:
        result = read_artifact(data, settings, logic)
    except (OSError, ValueError, KeyError, TypeError, pa.ArrowException) as exc:
        reason = 'version_mismatch' if isinstance(exc, ArtifactVersionMismatch) else 'read_error'
        LOGGER.warning('map artifact: fallback (reason=%s, file=%s, error=%s)', reason, name, type(exc).__name__)
        return None
    LOGGER.info('map artifact: loaded (file=%s, %s rows)', name, len(result[0]))
    return result
