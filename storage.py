"""Supabase Storage over its REST API (buckets: images, videos, audios)."""
import asyncio
import logging
from pathlib import Path
from urllib.parse import quote

import httpx

from config import SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_BUCKETS_PUBLIC, SIGNED_URL_SECONDS

log = logging.getLogger("storage")
_client: httpx.AsyncClient | None = None


class StorageError(RuntimeError):
    pass


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise StorageError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _client = httpx.AsyncClient(
            base_url=f"{SUPABASE_URL}/storage/v1",
            headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY},
            timeout=httpx.Timeout(600, connect=30),
        )
    return _client


def _check(response: httpx.Response, action: str) -> None:
    if response.status_code >= 400:
        raise StorageError(f"{action} failed ({response.status_code}): {response.text[:300]}")


def _object(bucket: str, path: str) -> str:
    return f"/object/{bucket}/{quote(path)}"


async def upload_bytes(bucket: str, path: str, data: bytes, content_type: str) -> str:
    response = await _http().post(_object(bucket, path), content=data,
                                  headers={"Content-Type": content_type, "x-upsert": "true"})
    _check(response, f"upload {bucket}/{path}")
    return path


async def upload_file(bucket: str, path: str, file: Path, content_type: str) -> str:
    data = await asyncio.to_thread(Path(file).read_bytes)
    return await upload_bytes(bucket, path, data, content_type)


async def download_to(bucket: str, path: str, dest: Path) -> Path:
    async with _http().stream("GET", _object(bucket, path)) as response:
        if response.status_code >= 400:
            await response.aread()
            _check(response, f"download {bucket}/{path}")
        with open(dest, "wb") as out:
            async for chunk in response.aiter_bytes():
                out.write(chunk)
    return dest


async def delete(bucket: str, paths: list[str]) -> None:
    paths = [p for p in paths if p]
    if not paths:
        return
    response = await _http().request("DELETE", f"/object/{bucket}", json={"prefixes": paths})
    _check(response, f"delete from {bucket}")


async def delete_quiet(bucket: str, paths: list[str | None]) -> None:
    """Delete, but never raise: a leftover file must not break the user's request."""
    try:
        await delete(bucket, [p for p in paths if p])
    except Exception as exc:
        log.warning("could not delete %s from %s: %s", paths, bucket, exc)


async def url(bucket: str, path: str | None) -> str | None:
    """A link the browser can load. Public buckets get a plain url, private ones a signed url."""
    if not path:
        return None
    if SUPABASE_BUCKETS_PUBLIC:
        return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{quote(path)}"
    response = await _http().post(f"/object/sign/{bucket}/{quote(path)}", json={"expiresIn": SIGNED_URL_SECONDS})
    _check(response, f"sign {bucket}/{path}")
    return f"{SUPABASE_URL}/storage/v1{response.json()['signedURL']}"
