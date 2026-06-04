import requests
import pandas as pd
import json
import time
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv


# ── 설정 ────────────────────────────────────────────────────────────────────

BASE_URL   = "https://api.fragella.com/api/v1"
LIMIT      = 50          # 브랜드당 최대 수집 수 (API 최대값)
DELAY      = 1.0         # 요청 간격 (초) - API 부하 방지
MAX_RETRY  = 3           # 실패 시 최대 재시도 횟수
RETRY_WAIT = 5           # 재시도 대기 시간 (초)

# 경로 설정
ROOT_DIR         = Path(__file__).resolve().parent.parent
BRAND_SOURCE_CSV = ROOT_DIR / "data" / "external" / "bigPerfumes.csv"
OUTPUT_CSV       = ROOT_DIR / "data" / "raw" / "fragella_raw.csv"
LOG_FILE         = ROOT_DIR / "data" / "raw" / "collection_log.json"


# ── API 키 로드 ──────────────────────────────────────────────────────────────

def load_api_key() -> str:
    load_dotenv(ROOT_DIR / ".env")
    api_key = os.getenv("FRAGELLA_API_KEY")
    if not api_key:
        raise SystemExit("⚠ .env 파일에 FRAGELLA_API_KEY가 없습니다.")
    return api_key


# ── 브랜드 목록 로드 ────────────────────────────────────────────────────────

def load_brands() -> list[str]:
    df = pd.read_csv(BRAND_SOURCE_CSV)
    brands = df["brand"].dropna().str.strip().unique().tolist()
    brands = sorted(brands)
    print(f"[브랜드 목록] {len(brands)}개 로드 완료")
    return brands


# ── API 호출 ────────────────────────────────────────────────────────────────

def fetch_brand(brand: str, headers: dict) -> list[dict] | None:
    url = f"{BASE_URL}/brands/{requests.utils.quote(brand, safe='')}"
    params = {"limit": LIMIT}

    for attempt in range(1, MAX_RETRY + 1):
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)

            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, list) else []

            elif res.status_code == 404:
                return []  # Fragella에 없는 브랜드

            elif res.status_code == 429:
                wait = RETRY_WAIT * attempt
                print(f"  ⚠ 429 Rate Limit - {wait}초 대기 후 재시도 ({attempt}/{MAX_RETRY})")
                time.sleep(wait)

            elif res.status_code == 401:
                raise SystemExit("⚠ API 키가 유효하지 않습니다. .env 파일을 확인하세요.")

            else:
                print(f"⚠ HTTP {res.status_code} - 재시도 ({attempt}/{MAX_RETRY})")
                time.sleep(RETRY_WAIT)

        except requests.exceptions.Timeout:
            print(f"⚠ Timeout - 재시도 ({attempt}/{MAX_RETRY})")
            time.sleep(RETRY_WAIT)

        except requests.exceptions.ConnectionError:
            print(f"⚠ 연결 오류 - 재시도 ({attempt}/{MAX_RETRY})")
            time.sleep(RETRY_WAIT)

    return None  # 최대 재시도 초과


# ── 체크포인트 ───────────────────────────────────────────────────────────────

def load_checkpoint() -> dict:
    # 이전 실행 로그가 있으면 이어서 수집
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "started_at": datetime.now().isoformat(),
        "completed_brands": [],   # 처리 완료 브랜드 (빈 응답 포함)
        "failed_brands": [],      # 최대 재시도 초과 브랜드
        "skipped_brands": [],     # Fragella에 없는 브랜드 (빈 응답)
        "brand_counts": {},       # 브랜드별 수집 수
        "total_collected": 0,
    }

def save_checkpoint(log: dict):
    log["updated_at"] = datetime.now().isoformat()
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


# ── 메인 수집 ────────────────────────────────────────────────────────────────

def collect():
    api_key = load_api_key()
    headers = {"x-api-key": api_key}

    # 출력 디렉토리 생성
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    # 브랜드 목록 로드
    brands = load_brands()

    # 체크포인트 로드
    log = load_checkpoint()
    done_brands = set(log["completed_brands"])

    remaining = [b for b in brands if b not in done_brands]
    print(f"[진행 상황] 완료: {len(done_brands)}개 / 남은 브랜드: {len(remaining)}개")
    print(f"[현재 수집량] {log['total_collected']}개\n")

    # 기존 CSV기 있으면 불러와서 이어쓰기
    if OUTPUT_CSV.exists() and log["total_collected"] > 0:
        existing_df = pd.read_csv(OUTPUT_CSV)
        all_records = existing_df.to_dict("records")
        print(f"[기존 데이터] {len(all_records)}행 로드\n")
    else:
        all_records = []

    # 수집 시작
    for i, brand in enumerate(remaining, 1):
        progress = len(done_brands) + i
        print(f"[{progress}/{len(brands)}] {brand}", end=" ... ", flush=True)

        result = fetch_brand(brand, headers)

        if result is None:
            print("실패 (재시도 초과)")
            log["failed_brands"].append(brand)

        elif len(result) == 0:
            print("— 없음")
            log["skipped_brands"].append(brand)
            log["completed_brands"].append(brand)

        else:
            all_records.extend(result)
            log["brand_counts"][brand] = len(result)
            log["total_collected"] += len(result)
            log["completed_brands"].append(brand)
            print(f"✓ {len(result)}개 (누적: {log['total_collected']}개)")

        # 10개 브랜드마다 저장
        if i % 10 == 0:
            _save_csv(all_records)
            save_checkpoint(log)

        time.sleep(DELAY)

    # 최종 저장
    _save_csv(all_records)
    log["finished_at"] = datetime.now().isoformat()
    save_checkpoint(log)

    # 결과 요약
    _print_summary(log, all_records)


# ── 저장 & 요약 ──────────────────────────────────────────────────────────────

def _save_csv(records: list[dict]):
    if not records:
        return
    df = pd.DataFrame(records)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")


def _print_summary(log: dict, records: list[dict]):
    print("\n" + "=" * 50)
    print("수집 완료 요약")
    print("=" * 50)
    print(f"총 수집 향수    : {log['total_collected']}개")
    print(f"수집 성공 브랜드: {len(log['brand_counts'])}개")
    print(f"없는 브랜드     : {len(log['skipped_brands'])}개")
    print(f"실패 브랜드     : {len(log['failed_brands'])}개")

    if log["failed_brands"]:
        print(f"\n⚠ 실패 브랜드 목록 (재시도 필요):")
        for b in log["failed_brands"]:
            print(f"  - {b}")

    if records:
        df = pd.DataFrame(records)
        print(f"\n고유 브랜드 수  : {df['Brand'].nunique()}개")
        print(f"저장 경로       : {OUTPUT_CSV}")


# ── 진입점 ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    collect()