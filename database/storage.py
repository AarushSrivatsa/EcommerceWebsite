"""Supabase Storage access through the official asynchronous Supabase client."""
import asyncio
import logging
from pathlib import Path

from supabase import AsyncClient, acreate_client

from config import (
    SIGNED_URL_SECONDS,
    SUPABASE_BUCKETS_PUBLIC,
    SUPABASE_SERVICE_KEY,
    SUPABASE_URL,
)

log = logging.getLogger("storage")
_client: AsyncClient | None = None
_client_lock = asyncio.Lock()


class StorageError(RuntimeError):
    """A storage operation failed or Supabase Storage is not configured."""


async def _get_client() -> AsyncClient:
    """Create the shared Supabase client lazily and reuse its connection pool."""
    global _client
    if _client is not None:
        return _client

    async with _client_lock:
        if _client is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
                raise StorageError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
            try:
                _client = await acreate_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            except Exception as exc:
                raise StorageError(f"could not initialize the Supabase client: {exc}") from exc

    return _client


async def close() -> None:
    """Close the shared client's connections during application shutdown."""
    global _client
    if _client is not None:
        client, _client = _client, None
        await client.aclose()


async def upload_bytes(bucket: str, path: str, data: bytes, content_type: str) -> str:
    try:
        client = await _get_client()
        await client.storage.from_(bucket).upload(
            path,
            data,
            file_options={"content-type": content_type, "upsert": "true"},
        )
    except Exception as exc:
        raise StorageError(f"upload {bucket}/{path} failed: {exc}") from exc
    return path


async def upload_file(bucket: str, path: str, file: Path, content_type: str) -> str:
    """Upload a local file using the SDK's supported filesystem-path input."""
    try:
        client = await _get_client()
        await client.storage.from_(bucket).upload(
            path,
            Path(file),
            file_options={"content-type": content_type, "upsert": "true"},
        )
    except Exception as exc:
        raise StorageError(f"upload {bucket}/{path} failed: {exc}") from exc
    return path

async def download_to(bucket: str, path: str, dest: Path) -> Path:
    """Download an object with the Supabase SDK and write it to the requested path."""
    try:
        client = await _get_client()
        data = await client.storage.from_(bucket).download(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(dest.write_bytes, data)
    except Exception as exc:
        raise StorageError(f"download {bucket}/{path} failed: {exc}") from exc
    return dest


async def delete(bucket: str, paths: list[str]) -> None:
    paths = [path for path in paths if path]
    if not paths:
        return
    try:
        client = await _get_client()
        await client.storage.from_(bucket).remove(paths)
    except Exception as exc:
        raise StorageError(f"delete from {bucket} failed: {exc}") from exc


async def delete_quiet(bucket: str, paths: list[str | None]) -> None:
    """Delete files without letting cleanup failures break the user's request."""
    try:
        await delete(bucket, [path for path in paths if path])
    except Exception as exc:
        log.warning("could not delete %s from %s: %s", paths, bucket, exc)


async def url(bucket: str, path: str | None) -> str | None:
    """Return a public URL or a time-limited signed URL for a stored object."""
    if not path:
        return None

    try:
        client = await _get_client()
        bucket_api = client.storage.from_(bucket)

        if SUPABASE_BUCKETS_PUBLIC:
            return await bucket_api.get_public_url(path)

        response = await bucket_api.create_signed_url(path, SIGNED_URL_SECONDS)
        signed_url = response.get("signedURL") or response.get("signedUrl")
        if not signed_url:
            raise StorageError(f"Supabase did not return a signed URL for {bucket}/{path}")
        if signed_url.startswith(("http://", "https://")):
            return signed_url
        return f"{SUPABASE_URL}/storage/v1{signed_url}"
    except StorageError:
        raise
    except Exception as exc:
        raise StorageError(f"create URL for {bucket}/{path} failed: {exc}") from exc
