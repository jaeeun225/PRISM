"""Upsert the versioned Parquet into the existing private Supabase bucket."""
import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.upload_data import read_settings
from src.storage_data import StorageClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--secrets', type=Path, default=ROOT/'.streamlit/secrets.toml')
    args = parser.parse_args()
    import app
    from src.map_artifact import artifact_filename, logic_version, read_artifact
    settings = read_settings(args.secrets)
    target = app.data_settings()
    logic = logic_version(ROOT)
    data = args.file.read_bytes()
    read_artifact(data, target, logic)  # Reject stale/mismatched artifacts before uploading.
    expected = artifact_filename(target['version'], logic)
    if args.file.name != expected:
        raise ValueError('Artifact filename does not match the current data/logic version')
    client = StorageClient(settings['SUPABASE_URL'], settings['SUPABASE_SERVICE_KEY'],
                           settings['SUPABASE_BUCKET'], 'map-artifacts/' + expected)
    bucket = client.ensure_private_bucket()
    limit = bucket.get('file_size_limit')
    if limit is not None and len(data) > int(limit):
        raise ValueError('Artifact exceeds bucket size limit')
    client.request('POST', '/object/' + client.object_path, data=data, headers={
        'Content-Type': 'application/vnd.apache.parquet', 'x-upsert': 'true', 'Cache-Control': 'no-cache'})
    if hashlib.sha256(client.download()).digest() != hashlib.sha256(data).digest():
        raise ValueError('Uploaded artifact hash mismatch')
    print(f'Private upload verified: map-artifacts/{expected}; bytes={len(data):,}')


if __name__ == '__main__':
    main()
