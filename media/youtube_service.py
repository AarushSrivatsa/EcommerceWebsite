"""Uploads the final video to the selected YouTube channel, using the credentials stored for it."""
import asyncio
import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import crypto
import database.database as db
import database.storage as storage
from config import OUTPUT_DIR, VIDEOS_BUCKET
from media.youtube_uploader import upload_video

log = logging.getLogger("youtube_service")

TOKEN_URI = "https://oauth2.googleapis.com/token"


def _google_credentials(stored: dict) -> Credentials:
    return Credentials(token=None, refresh_token=stored["refresh_token"], client_id=stored["client_id"],
                       client_secret=stored["client_secret"], token_uri=stored["token_uri"])


def check_credentials(stored: dict) -> None:
    """Raises if Google does not accept them (wrong client secret, revoked or invalid refresh token)."""
    _google_credentials(stored).refresh(Request())


def _upload(stored: dict, video: Path, meta: dict) -> str:
    youtube = build("youtube", "v3", credentials=_google_credentials(stored))
    return upload_video(youtube, video, meta["title"], meta["description"], meta["tags"],
                        meta["category_id"], meta["privacy"])


async def upload_job(script_id: uuid.UUID, channel_id: uuid.UUID, meta: dict) -> None:
    """The caller has already set youtube_status to 'uploading'; this ends it as done or failed."""
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="youtube-", dir=OUTPUT_DIR))
    try:
        state = await db.get_state(script_id)
        channel = await db.get_channel(channel_id)
        if state is None or not state.final_video_path:
            raise RuntimeError("the script has no final video")
        if channel is None:
            raise RuntimeError("the YouTube channel was removed")
        stored = crypto.decrypt(channel.credentials)
        video = await storage.download_to(VIDEOS_BUCKET, state.final_video_path, folder / "final.mp4")
        url = await asyncio.to_thread(_upload, stored, video, meta)
        await db.set_state_fields(script_id, youtube_status="done", youtube_url=url, youtube_error=None)
    except Exception as exc:
        log.exception("youtube upload failed for %s", script_id)
        await db.set_state_fields(script_id, youtube_status="failed",
                                  youtube_error=f"{type(exc).__name__}: {exc}"[:500])
    finally:
        shutil.rmtree(folder, ignore_errors=True)
