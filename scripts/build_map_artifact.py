"""Build a private map Parquet artifact using the existing app functions."""
import argparse
import hashlib
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, default=ROOT/'data/processed/fragella_processed.csv')
    parser.add_argument('--source', choices=['supabase', 'local'], default='supabase',
                        help='Target app settings; computation always uses the supplied local CSV.')
    args = parser.parse_args()
    os.environ['SCENT_DATA_SOURCE'] = args.source
    if args.source == 'local':
        os.environ['SCENT_CSV_PATH'] = str(args.csv.resolve())
    import app
    from src.map_artifact import MAP_COLUMNS, artifact_filename, logic_version, write_artifact
    settings = app.data_settings()
    # Explicitly use the original pipeline, never load an existing artifact.
    df, angles = app.load_scent_map(source='local', csv_path=str(args.csv.resolve()),
                                    version=settings['version'])
    view = app.prepare_view(df[MAP_COLUMNS], angles)
    view['marker_rgb'] = view.plot_color.map(app.marker_rgb)
    view['marker_border'] = view.marker_rgb.map(app.darker_border)
    view['marker_text'] = view.marker_rgb.map(app.contrast_text_color)
    logic = logic_version(ROOT)
    path = ROOT/'data/artifacts'/artifact_filename(settings['version'], logic)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_artifact(path, view, angles, settings, logic, hashlib.sha256(args.csv.read_bytes()).hexdigest())
    print(f'Artifact: {path.name}; rows={len(view):,}; bytes={path.stat().st_size:,}')
    print(f'File: {path}')


if __name__ == '__main__':
    main()
