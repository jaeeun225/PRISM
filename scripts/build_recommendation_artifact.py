"""Build a private, versioned recommendation artifact from the local source CSV."""
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
                        help='Target app settings; computation uses the supplied local CSV.')
    args = parser.parse_args()
    os.environ['SCENT_DATA_SOURCE'] = args.source
    if args.source == 'local':
        os.environ['SCENT_CSV_PATH'] = str(args.csv.resolve())
    import app
    from src.recommendation_artifact import artifact_filename, logic_version, write_artifact

    settings = app.data_settings()
    df = app.get_catalog(source='local', csv_path=str(args.csv.resolve()), version=settings['version'])
    accords = app.build_accord_matrix(df)
    notes = app.build_note_matrix(df)
    catalog = df[['_id', 'Name', 'Brand']].copy()
    images = df['Image URL'] if 'Image URL' in df else app.pd.Series(None, index=df.index)
    catalog['Image URL'] = images.map(app.image_url_or_none)
    logic = logic_version(ROOT)
    path = ROOT/'data/artifacts'/artifact_filename(settings['version'], logic)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_artifact(path, catalog, accords, notes, settings, logic,
                   hashlib.sha256(args.csv.read_bytes()).hexdigest())
    print(f'File: {path}')
    print(f'Rows={len(catalog):,}; accords={accords.shape}; notes={notes.shape}; '
          f'nnz={notes.nnz:,}; bytes={path.stat().st_size:,}')


if __name__ == '__main__':
    main()
