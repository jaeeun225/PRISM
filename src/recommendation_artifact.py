"""Private recommendation snapshots: Parquet catalog + NumPy/CSR, never pickle."""
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
import re
from zipfile import BadZipFile, ZIP_STORED, ZipFile
import zlib

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from .storage_data import DataLoadError, StorageClient, StorageError
from .map_artifact import ArtifactVersionMismatch, function_source

LOGGER = logging.getLogger('streamlit.prism.recommendation_artifact')
LOGGER.setLevel(logging.INFO)
if not LOGGER.handlers:
    LOGGER.addHandler(logging.StreamHandler())
LOGGER.propagate = False

SCHEMA_VERSION = 1
CATALOG_COLUMNS = ['_id', 'Name', 'Brand', 'Image URL']
MEMBERS = {'catalog.parquet', 'accord.npy', 'notes.npz'}


def logic_version(root):
    root = Path(root)
    digest = hashlib.sha256()
    for name in ('src/recommender.py', 'src/scent_map.py'):
        digest.update((root/name).read_text(encoding='utf-8').encode())
    digest.update(function_source((root/'app.py').read_text(encoding='utf-8'), {'image_url_or_none'}))
    digest.update(Path(__file__).read_text(encoding='utf-8').encode())
    return digest.hexdigest()[:16]


def artifact_filename(version, logic):
    readable = re.sub(r'[^A-Za-z0-9._-]+', '-', version).strip('-')[:100]
    suffix = hashlib.sha256(version.encode()).hexdigest()[:8]
    return f'recommendation-{readable}-{suffix}-logic-{logic}.zip'


def _validate(catalog, accords, notes):
    if list(catalog.columns) != CATALOG_COLUMNS or catalog['_id'].isna().any() or catalog['_id'].duplicated().any():
        raise ValueError('Invalid recommendation catalog/ID mapping')
    if accords.shape != (len(catalog), 14) or notes.ndim != 2 or notes.shape[0] != len(catalog):
        raise ValueError('Recommendation matrix rows do not match catalog')
    if accords.dtype != np.float32 or notes.dtype != np.float32 or notes.format != 'csr':
        raise ValueError('Invalid recommendation matrix format')
    if not np.isfinite(accords).all() or not np.isfinite(notes.data).all():
        raise ValueError('Invalid recommendation matrix values')
    notes.check_format(full_check=True)


def write_artifact(path, catalog, accords, notes, settings, logic, csv_sha256):
    from scipy.sparse import save_npz

    _validate(catalog, accords, notes)
    catalog_bytes, accord_bytes, note_bytes = BytesIO(), BytesIO(), BytesIO()
    pq.write_table(pa.Table.from_pandas(catalog, preserve_index=False), catalog_bytes, compression='zstd')
    np.save(accord_bytes, accords, allow_pickle=False)
    save_npz(note_bytes, notes, compressed=True)
    parts = {'catalog.parquet': catalog_bytes.getvalue(), 'accord.npy': accord_bytes.getvalue(),
             'notes.npz': note_bytes.getvalue()}
    metadata = {'schema': SCHEMA_VERSION, 'version': settings['version'], 'logic': logic,
                'source': settings['source'], 'object_path': settings.get('object_path', ''),
                'csv_sha256': csv_sha256, 'rows': len(catalog), 'note_columns': notes.shape[1],
                'sha256': {name: hashlib.sha256(value).hexdigest() for name, value in parts.items()}}
    # Inner Parquet/CSR payloads already use compression; avoid compressing twice.
    with ZipFile(path, 'w', compression=ZIP_STORED) as archive:
        archive.writestr('manifest.json', json.dumps(metadata, ensure_ascii=False))
        for name, value in parts.items():
            archive.writestr(name, value)


def read_artifact(data, settings, logic):
    with ZipFile(BytesIO(data) if isinstance(data, bytes) else data) as archive:
        if len(archive.namelist()) != 4 or set(archive.namelist()) != MEMBERS | {'manifest.json'}:
            raise ValueError('Incomplete recommendation artifact')
        metadata = json.loads(archive.read('manifest.json'))
        expected = {'schema': SCHEMA_VERSION, 'version': settings['version'], 'logic': logic,
                    'source': settings['source'], 'object_path': settings.get('object_path', '')}
        if any(metadata.get(key) != value for key, value in expected.items()):
            raise ArtifactVersionMismatch('Recommendation artifact version mismatch')
        parts = {name: archive.read(name) for name in MEMBERS}
    if any(hashlib.sha256(value).hexdigest() != metadata['sha256'][name] for name, value in parts.items()):
        raise ValueError('Recommendation artifact checksum mismatch')
    from scipy.sparse import load_npz

    catalog = pq.read_table(BytesIO(parts['catalog.parquet'])).to_pandas()
    accords = np.load(BytesIO(parts['accord.npy']), allow_pickle=False)
    notes = load_npz(BytesIO(parts['notes.npz']))
    _validate(catalog, accords, notes)
    if len(catalog) != metadata['rows'] or notes.shape[1] != metadata['note_columns']:
        raise ValueError('Recommendation artifact dimensions mismatch')
    return catalog, accords, notes


def load_artifact_or_none(settings, logic, root):
    name = artifact_filename(settings['version'], logic)
    try:
        if settings['source'] == 'local':
            data = (Path(root)/'data/artifacts'/name).read_bytes()
        else:
            data = StorageClient(settings['url'], settings['service_key'], settings['bucket'],
                                 'map-artifacts/' + name).download()
    except (DataLoadError, OSError) as exc:
        missing = isinstance(exc, FileNotFoundError) or (isinstance(exc, StorageError) and exc.status == 404)
        reason = 'missing' if missing else 'download_error'
        LOGGER.warning('recommendation artifact: fallback (reason=%s, file=%s, error=%s)',
                       reason, name, type(exc).__name__)
        return None
    try:
        result = read_artifact(data, settings, logic)
    except (OSError, ValueError, KeyError, TypeError, BadZipFile, EOFError, zlib.error,
            pa.ArrowException) as exc:
        reason = 'version_mismatch' if isinstance(exc, ArtifactVersionMismatch) else 'read_error'
        LOGGER.warning('recommendation artifact: fallback (reason=%s, file=%s, error=%s)',
                       reason, name, type(exc).__name__)
        return None
    LOGGER.info('recommendation artifact: loaded (file=%s, %s rows)', name, len(result[0]))
    return result
