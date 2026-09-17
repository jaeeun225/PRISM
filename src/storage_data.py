"""Minimal server-side Supabase Storage REST client (no public URLs)."""

import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class DataLoadError(RuntimeError):
    """A safe, user-facing error without credentials or response bodies."""


class StorageError(DataLoadError):
    def __init__(self, status: int, code: str = ""):
        self.status = status
        self.code = code
        if status in (401, 403) or code in ("InvalidJWT", "AccessDenied", "Unauthorized"):
            message = "Storage 인증 실패: Supabase URL과 서비스 키 및 접근 권한을 확인하세요."
        elif status == 404 or code in ("NoSuchBucket", "NoSuchKey", "not_found"):
            message = "Storage 버킷 또는 CSV를 찾을 수 없습니다. 버킷/경로와 업로드 여부를 확인하세요."
        elif status == 413 or code in ("EntityTooLarge", "PayloadTooLarge"):
            message = "Storage 파일 크기 제한 초과: 프로젝트와 버킷의 업로드 한도를 확인하세요."
        else:
            message = f"Storage 요청 실패(HTTP {status}): URL, 키, 버킷 설정 또는 서비스 상태를 확인하세요."
        super().__init__(message)


class _NoRedirect(HTTPRedirectHandler):
    # Never forward service credentials to an unexpected redirect destination.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_settings(url: str, key: str, bucket: str, object_path: str) -> None:
    if not url or not key:
        raise DataLoadError("Supabase 설정 누락: st.secrets의 SUPABASE_URL과 SUPABASE_SERVICE_KEY를 입력하세요.")
    if any(char.isspace() for char in key):
        raise DataLoadError("Supabase 서비스 키 형식을 확인하세요. 공백이나 줄바꿈을 포함할 수 없습니다.")
    try:
        parts = urlsplit(url)
    except ValueError:
        raise DataLoadError("SUPABASE_URL 형식을 확인하세요.") from None
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        raise DataLoadError("SUPABASE_URL은 https://프로젝트.supabase.co 형식의 프로젝트 URL이어야 합니다.")
    if not bucket or "/" in bucket or bucket in (".", ".."):
        raise DataLoadError("SUPABASE_BUCKET에 올바른 버킷 이름을 입력하세요.")
    if not object_path or any(part in ("", ".", "..") for part in object_path.split("/")):
        raise DataLoadError("SUPABASE_OBJECT_PATH에 올바른 Storage 파일 경로를 입력하세요.")


class StorageClient:
    def __init__(self, url: str, key: str, bucket: str, object_path: str):
        validate_settings(url, key, bucket, object_path)
        self.base_url = url.rstrip("/") + "/storage/v1"
        self.bucket_path = "/bucket/" + quote(bucket, safe="")
        self.object_path = quote(bucket, safe="") + "/" + quote(object_path, safe="/")
        self.bucket = bucket
        self.headers = {"apikey": key}
        # Legacy service_role JWTs use Bearer auth; modern sb_secret keys use apikey.
        if not key.startswith("sb_secret_"):
            self.headers["Authorization"] = "Bearer " + key
        self.opener = build_opener(_NoRedirect())

    def request(self, method: str, path: str, *, data=None, headers=None) -> bytes:
        request = Request(self.base_url + path, data=data, method=method,
                          headers={**self.headers, **(headers or {})})
        try:
            with self.opener.open(request, timeout=300) as response:
                return response.read()
        except HTTPError as exc:
            try:
                payload = json.loads(exc.read())
                code = str(payload.get("code", payload.get("error", "")))
                status = int(payload.get("statusCode", exc.code))
            except (ValueError, TypeError, AttributeError):
                code, status = "", exc.code
            finally:
                exc.close()
            raise StorageError(status, code) from None
        except (URLError, TimeoutError, OSError, HTTPException):
            raise DataLoadError("Storage 연결 실패: 네트워크, Supabase URL 및 프로젝트 실행 상태를 확인하세요.") from None

    def get_bucket(self) -> dict:
        try:
            value = json.loads(self.request("GET", self.bucket_path))
            if not isinstance(value, dict):
                raise ValueError
            return value
        except (ValueError, TypeError):
            raise DataLoadError("Storage 버킷 정보를 읽을 수 없습니다.") from None

    def require_private_bucket(self) -> dict:
        bucket = self.get_bucket()
        if bucket.get("public") is not False:
            raise DataLoadError("Storage 버킷이 private이 아닙니다. private 버킷을 지정하세요.")
        return bucket

    def ensure_private_bucket(self) -> dict:
        try:
            return self.require_private_bucket()
        except StorageError as exc:
            if exc.status != 404 and exc.code not in ("NoSuchBucket", "not_found"):
                raise
        try:
            self.request("POST", "/bucket", data=json.dumps({
                "id": self.bucket, "name": self.bucket, "public": False,
            }).encode("utf-8"), headers={"Content-Type": "application/json"})
        except StorageError as exc:
            # Another invocation may have created the bucket in the meantime.
            if exc.status != 409 and exc.code not in ("Duplicate", "ResourceAlreadyExists"):
                raise
        return self.require_private_bucket()

    def download(self) -> bytes:
        self.require_private_bucket()
        return self.request("GET", "/object/authenticated/" + self.object_path)

    def upload(self, data: bytes) -> None:
        self.request("POST", "/object/" + self.object_path, data=data, headers={
            "Content-Type": "application/gzip", "x-upsert": "true", "Cache-Control": "no-cache",
        })
