"""Create a private bucket and upsert a gzip CSV, then verify compressed and original hashes.

Run from the project root: python scripts/upload_data.py
Credentials: .streamlit/secrets.toml or SUPABASE_* environment variables.
"""

import argparse
import hashlib
import gzip
import os
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.storage_data import DataLoadError, StorageClient


def read_settings(path: Path) -> dict:
    values = {}
    if path.exists():
        try:
            values = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            raise DataLoadError("Secrets 파일을 읽을 수 없습니다. TOML 형식을 확인하세요.") from None
    defaults = {"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": "",
                "SUPABASE_BUCKET": "prism-data", "SUPABASE_OBJECT_PATH": "fragella_processed.csv.gz"}
    return {name: str(os.environ.get(name, values.get(name, default))).strip()
            for name, default in defaults.items()}


def upload_data(csv_path: Path, settings: dict) -> None:
    if not settings["SUPABASE_OBJECT_PATH"].endswith(".csv.gz"):
        raise DataLoadError("SUPABASE_OBJECT_PATH를 .csv.gz 경로로 설정하세요.")
    client = StorageClient(settings["SUPABASE_URL"], settings["SUPABASE_SERVICE_KEY"],
                           settings["SUPABASE_BUCKET"], settings["SUPABASE_OBJECT_PATH"])
    try:
        data = csv_path.read_bytes()
    except OSError:
        raise DataLoadError("업로드할 로컬 CSV를 읽을 수 없습니다.") from None
    if not data:
        raise DataLoadError("CSV 파일이 비어 있습니다. 업로드를 중단합니다.")
    original_hash = hashlib.sha256(data).digest()
    original_size = len(data)
    data = gzip.compress(data, compresslevel=9, mtime=0)
    metadata = client.ensure_private_bucket()
    limit = metadata.get("file_size_limit")
    if limit is not None and len(data) > int(limit):
        raise DataLoadError("gzip 파일이 버킷의 file_size_limit을 초과합니다. Supabase Storage 설정을 확인하세요.")
    print(f"CSV: {original_size:,} bytes; gzip: {len(data):,} bytes")
    print(f"Uploading {len(data):,} bytes to a private bucket (upsert)...")
    client.upload(data)
    downloaded = client.download()
    if hashlib.sha256(downloaded).digest() != hashlib.sha256(data).digest():
        raise DataLoadError("업로드 후 해시 검증에 실패했습니다. 스크립트를 다시 실행하세요.")
    if hashlib.sha256(gzip.decompress(downloaded)).digest() != original_hash:
        raise DataLoadError("압축 해제 후 원본 CSV 해시 검증에 실패했습니다.")
    print("Upload verified: gzip and decompressed CSV hashes match. Bucket is private.")
    print("If the app is already running, bump SCENT_DATA_VERSION or clear/reboot its cache.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "data/processed/fragella_processed.csv")
    parser.add_argument("--secrets", type=Path, default=ROOT / ".streamlit/secrets.toml")
    args = parser.parse_args()
    try:
        upload_data(args.csv, read_settings(args.secrets))
    except DataLoadError as exc:
        print(f"Upload failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
