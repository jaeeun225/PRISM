# PRISM : Perfume Recommendation & Interactive Scent Map
A fragrance discovery system that delivers personalized recommendations, visualizes scent structures through an interactive Scent Map, and builds your unique fragrance profile — helping you explore and understand the world of perfume with ease.

웹 서비스: https://my-prism.streamlit.app

## 개요

향수 취향을 색과 위치로 시각화하고, 같은 지도 위에서 유사 향수 추천과 개인 향 프로필을 제공하는 웹 서비스입니다. 향수의 어코드를 Michael Edwards의 Fragrance Wheel 14개 섹션 기준의 위치와 색으로 지도(Scent Map)에 배치합니다. 데이터는 Fragella API로 수집·정제한 향수 38,476종입니다.

## 주요 기능

- **향 지도(Scent Map)**: 어코드를 14개 섹션 방향의 벡터로 바꾸고 강도(Dominant 8 · Prominent 4 · Moderate 2 · Subtle 1)로 가중한 원형 평균을 향수의 위치로 씁니다. 색도 같은 위치에서 정합니다. 확대·이동, 툴팁, 어코드 필터를 지원합니다.
- **추천**: 기준 향수 1개를 고르면 `0.8 × 어코드(14차원) 코사인 유사도 + 0.2 × 노트(멀티 핫, 탑·미들·베이스 1:2:3) 유사도`로 Top 10을 계산해 지도에 번호로 표시합니다.
- **프로필**: 시그니처 향수 최대 3개로 계열 비율과 자주 쓰인 노트를 요약한 카드를 만들어 PNG로 저장합니다. 선택은 향수 ID만 URL에 담아 복원하며 로그인과 개인정보 수집이 없습니다.
- **언어**: 화면 문구를 한국어와 영어로 전환합니다(KO | EN).

## 구조

| 경로 | 내용 |
| --- | --- |
| `app.py` | Streamlit 진입점(탭, 헤더, 주소 처리) |
| `src/scent_map.py` | 어코드→섹션 매핑, 위치·색 계산 |
| `src/recommender.py` | 어코드·노트 행렬, 유사도 추천 |
| `src/scent_profile.py`, `profile_page.py`, `profile_card.py`, `profile_state.py`, `profile_labels.py` | 프로필 요약, 화면, PNG 카드, URL 상태, 표시 문구 |
| `src/integrated_map.py`, `integrated_ui.py`, `catalog_search.py`, `accord_descriptions.py`, `i18n.py` | 통합 화면(검색·필터·지도·목록·상세 카드), 어코드 설명, 한·영 문구 |
| `src/storage_data.py`, `map_artifact.py`, `recommendation_artifact.py` | 비공개 저장소 로딩, 사전 계산 파일 로딩(없으면 CSV로 직접 계산) |
| `src/collect_fragella.py` | Fragella API 수집 |
| `scripts/` | 데이터·산출물 업로드, 산출물 생성 |
| `notebooks/` | `01_eda`, `02_preprocess`, `03_scent_map` |
| `assets/` | 로고, 프로필 카드용 글꼴 |

## 데이터 안내

수집·정제한 CSV와 지도·추천 사전 계산 파일은 Fragella API 데이터의 저작권을 고려해 이 저장소에 포함하지 않습니다. 배포 환경에서는 비공개 Supabase Storage에서 서버만 읽어 사용하고, `data/processed/`, `data/artifacts/`, `.streamlit/secrets.toml`은 Git에서 제외합니다.

## Streamlit Scent Map 실행 및 배포

Python 3.11 이상을 사용합니다(개발은 3.12.7). 기본 데이터 소스는 Supabase private Storage이며, 추가 SDK 없이 Python 표준 라이브러리로 Storage REST API를 호출합니다.

### 1. 로컬 Secrets 설정

프로젝트 루트에서 실행합니다.

```powershell
python -m pip install -r requirements.txt
Copy-Item .streamlit/secrets.toml.example .streamlit/secrets.toml
```

이미 `.streamlit/secrets.toml`이 있으면 복사로 덮어쓰지 말고 해당 파일을 편집합니다. 다음 값을 입력합니다.

```toml
SUPABASE_URL = ""          # Supabase 프로젝트 URL
SUPABASE_SERVICE_KEY = ""  # 서버 전용 service_role JWT 또는 sb_secret_ 키
SUPABASE_BUCKET = "prism-data"
SUPABASE_OBJECT_PATH = "fragella_processed.csv.gz"
SCENT_DATA_VERSION = "1"
```

프로젝트 URL과 서버 키는 Supabase 프로젝트 설정에서 확인합니다. 키는 Streamlit 서버에서만 사용되며 Plotly나 브라우저로 전송하지 않습니다. 이 구현은 서비스 키를 사용하며 anon 키에 대한 공개 읽기 정책을 추가하지 않습니다. 앱에서는 `st.secrets`로 설정을 읽고, 업로드 스크립트는 동일한 TOML 파일 또는 같은 이름의 환경변수를 읽습니다(환경변수 우선).

### 2. CSV 일회성 업로드

```powershell
python scripts/upload_data.py
```

- 버킷이 없으면 `public=false`로 생성합니다. 기존 버킷이 public이면 업로드를 중단합니다.
- 원본 `data/processed/fragella_processed.csv`를 메모리에서 gzip(level=9, mtime=0)으로 압축해 `fragella_processed.csv.gz`로 업로드합니다. 원본 파일을 변경하거나 압축 파일을 Git에 저장하지 않습니다. 반복 실행 시 같은 객체를 upsert합니다.
- 업로드 후 인증된 다운로드로 gzip 바이트의 SHA-256을 비교하고, 압축 해제한 내용도 원본 CSV 해시와 비교합니다. private 설정을 다시 확인합니다.
- 다른 파일/설정 경로가 필요하면 `--csv`와 `--secrets` 옵션을 사용합니다.
- 업로드 한도는 원본 CSV가 아닌 gzip 압축 후 크기에 적용됩니다. 스크립트가 압축 전후 크기를 출력합니다. 기존 버킷에 MIME 제한이 있다면 `application/gzip`을 허용해야 합니다.
- 네트워크 중단이나 크기 제한 오류가 발생하면 원인을 해결한 뒤 같은 명령으로 재실행합니다.

### 3. 실행과 로컬 데이터 전환

Supabase에서 로드:

```powershell
$env:SCENT_DATA_SOURCE = "supabase"
streamlit run app.py
```

키 없이 로컬 CSV로 개발:

```powershell
$env:SCENT_DATA_SOURCE = "local"
streamlit run app.py
```

로컬 모드에는 CSV(기본 경로 `data/processed/fragella_processed.csv`)가 필요합니다. CSV는 저장소에 포함되어 있지 않으며, 필요하면 `SCENT_CSV_PATH` 환경변수로 경로를 지정합니다. 상대 경로는 프로젝트 루트를 기준으로 해석합니다. 지도·추천 사전 계산 파일(`data/artifacts/`)이 없으면 CSV에서 직접 계산하므로 첫 로딩이 느릴 수 있습니다. 산출물 생성과 업로드는 `scripts/MAP_ARTIFACT.md`, `scripts/RECOMMENDATION_ARTIFACT.md`를 참고합니다. 원격 실패를 조용히 로컬 데이터로 대체하지 않으며, 명시적으로 local 모드를 선택합니다.

다운로드, CSV 파싱, 좌표/색상 계산은 `st.cache_data(ttl=86400)`로 24시간 캐싱되어 같은 서버의 세션/재실행에서 재사용됩니다. 원격 CSV를 교체한 직후에는 `SCENT_DATA_VERSION`을 올리거나 앱 캐시를 지우고 재시작합니다. 원격 파일은 `pd.read_csv(..., compression="gzip")`으로 읽고, 로컬 CSV는 기존처럼 읽습니다. 기존 Cloud Secrets의 `SUPABASE_OBJECT_PATH`도 `fragella_processed.csv.gz`로 바꾸세요. CSV는 서버 메모리에서 읽으며 앱이 별도 파일로 저장하지 않습니다.

### 4. Streamlit Community Cloud

1. GitHub 저장소에 `app.py`, `requirements.txt`, `src/`, `assets/`, `scripts/`, `.streamlit/config.toml`, `.streamlit/secrets.toml.example`, `README.md`를 포함합니다. CSV, 사전 계산 파일, 실제 Secrets는 포함하지 않습니다.
2. 앱 생성 시 저장소/브랜치와 진입 파일 `app.py`를 선택하고, 앱 설정에서 Python 버전을 선택합니다(현재 배포는 3.14).
3. 배포 화면 **Advanced settings → Secrets**에 로컬 `secrets.toml`과 같은 TOML 설정을 입력합니다. 기존 앱은 **App settings → Secrets**에서 수정합니다.
4. Storage 업로드를 마친 뒤 배포합니다. `SCENT_DATA_SOURCE`를 설정하지 않으면 기본값인 supabase 모드로 실행됩니다.
5. 지도가 표시되고, 확대/축소와 이름·브랜드·accord 툴팁이 동작하는지, 향수를 검색해 추천 Top 10이 지도에 표시되는지 확인합니다.

Storage 연결, 인증, 파일 누락, CSV 형식 오류는 앱에 안내됩니다. 실제 URL/키나 서버 응답 본문은 오류 화면에 출력하지 않습니다.

### 5. Git 제외 확인

기존 `.gitignore`의 `data/processed/`와 `.streamlit/secrets.toml` 규칙을 유지합니다. 예외 규칙을 추가하거나 `git add -f`로 우회하지 않습니다.

```powershell
git check-ignore data/processed/fragella_processed.csv .streamlit/secrets.toml
git ls-files -- data/processed/fragella_processed.csv .streamlit/secrets.toml
git status --short --untracked-files=all
```

첫 명령은 두 경로를 출력하고, 두 번째 명령은 아무것도 출력하지 않아야 합니다. 실제 Secrets와 CSV는 커밋 대상에 나타나면 안 됩니다.

공식 문서: [Supabase Storage 접근 제어](https://supabase.com/docs/guides/storage/security/access-control), [파일 크기 제한](https://supabase.com/docs/guides/storage/uploads/file-limits), [Streamlit Cloud Secrets](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).
