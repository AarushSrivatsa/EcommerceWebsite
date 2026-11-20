"""YouTube channel CRUD and resumable video uploads."""
import asyncio
import httplib2
import logging
import mimetypes
import random
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

import crypto
import database.storage as storage
import deps
from config import OUTPUT_DIR, VIDEOS_BUCKET
from database.initialization import SessionLocal
from database.models import State, YoutubeChannel

router = APIRouter(tags=["youtube"])
log = logging.getLogger("youtube")
TOKEN_URI = "https://oauth2.googleapis.com/token"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024
MAX_UPLOAD_RETRIES = 5


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)


class ChannelOut(BaseModel):
    id: uuid.UUID
    name: str
    is_selected: bool


class UploadIn(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    category_id: str = "22"
    privacy: Literal["private", "unlisted", "public"] = "private"


class UploadOut(BaseModel):
    status: str
    url: str | None
    error: str | None


def _google_credentials(stored: dict) -> Credentials:
    return Credentials(
        token=None,
        refresh_token=stored["refresh_token"],
        client_id=stored["client_id"],
        client_secret=stored["client_secret"],
        token_uri=stored.get("token_uri", TOKEN_URI),
        scopes=YOUTUBE_SCOPES,
    )


def _check_google_credentials(stored: dict) -> None:
    credentials = _google_credentials(stored)
    credentials.refresh(Request())


def _upload_video(stored: dict, video_path: Path, meta: dict) -> str:
    """Upload with the same resumable chunks and retry behavior as the local uploader."""
    credentials = _google_credentials(stored)
    credentials.refresh(Request())
    youtube = build("youtube", "v3", credentials=credentials)

    mime_type = mimetypes.guess_type(str(video_path))[0] or "application/octet-stream"
    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": meta["category_id"],
        },
        "status": {"privacyStatus": meta["privacy"]},
    }
    media = MediaFileUpload(
        str(video_path),
        mimetype=mime_type,
        chunksize=UPLOAD_CHUNK_SIZE,
        resumable=True,
    )
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    retries = 0
    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as exc:
            if exc.resp.status not in {500, 502, 503, 504} or retries >= MAX_UPLOAD_RETRIES:
                raise
            delay = min(2 ** retries, 32) + random.random()
            log.warning("Temporary YouTube API error %s; retrying in %.1fs", exc.resp.status, delay)
            time.sleep(delay)
            retries += 1
        except (OSError, httplib2.HttpLib2Error, RefreshError):
            if retries >= MAX_UPLOAD_RETRIES:
                raise
            delay = min(2 ** retries, 32) + random.random()
            log.warning("Temporary YouTube connection error; retrying in %.1fs", delay)
            time.sleep(delay)
            retries += 1

    video_id = response.get("id") if response else None
    if not video_id:
        raise RuntimeError(f"YouTube upload response did not contain a video ID: {response}")
    return f"https://www.youtube.com/watch?v={video_id}"


async def _upload_job(script_id: uuid.UUID, channel_id: uuid.UUID, metadata: dict) -> None:
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="youtube-", dir=OUTPUT_DIR))
    try:
        async with SessionLocal() as session:
            state = await session.get(State, script_id)
            channel = await session.get(YoutubeChannel, channel_id)

        if state is None or not state.final_video_path:
            raise RuntimeError("the script has no final video")
        if channel is None:
            raise RuntimeError("the selected YouTube channel was deleted")

        credentials = crypto.decrypt(channel.credentials)
        video_file = await storage.download_to(
            VIDEOS_BUCKET,
            state.final_video_path,
            folder / "final.mp4",
        )
        url = await asyncio.to_thread(_upload_video, credentials, video_file, metadata)

        async with SessionLocal() as session:
            await session.execute(
                update(State)
                .where(State.id == script_id)
                .values(youtube_status="done", youtube_url=url, youtube_error=None)
            )
            await session.commit()
    except Exception as exc:
        log.exception("YouTube upload failed for script %s", script_id)
        async with SessionLocal() as session:
            await session.execute(
                update(State)
                .where(State.id == script_id)
                .values(
                    youtube_status="failed",
                    youtube_error=f"{type(exc).__name__}: {exc}"[:500],
                )
            )
            await session.commit()
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@router.post("/youtube/channels", response_model=ChannelOut, status_code=201)
async def add_channel(body: ChannelCreate):
    stored = {
        "client_id": body.client_id.strip(),
        "client_secret": body.client_secret.strip(),
        "token_uri": TOKEN_URI,
        "refresh_token": body.refresh_token.strip(),
    }
    try:
        await asyncio.to_thread(_check_google_credentials, stored)
    except Exception as exc:
        raise HTTPException(400, f"Google did not accept these credentials: {exc}") from exc

    async with SessionLocal() as session:
        channel_count = await session.scalar(
            select(func.count()).select_from(YoutubeChannel)
        )
        channel = YoutubeChannel(
            name=body.name.strip(),
            credentials=crypto.encrypt(stored),
            is_selected=(channel_count == 0),
        )
        session.add(channel)
        await session.commit()
        await session.refresh(channel)

    return ChannelOut(
        id=channel.id,
        name=channel.name,
        is_selected=channel.is_selected,
    )


@router.get("/youtube/channels", response_model=list[ChannelOut])
async def list_channels():
    async with SessionLocal() as session:
        channels = list((
            await session.execute(
                select(YoutubeChannel).order_by(YoutubeChannel.created_at)
            )
        ).scalars())

    return [
        ChannelOut(
            id=channel.id,
            name=channel.name,
            is_selected=channel.is_selected,
        )
        for channel in channels
    ]


@router.post("/youtube/channels/{channel_id}/select", response_model=list[ChannelOut])
async def select_channel(channel_id: uuid.UUID):
    async with SessionLocal() as session:
        channel = await session.get(YoutubeChannel, channel_id)
        if channel is None:
            raise HTTPException(404, "channel not found")

        await session.execute(
            update(YoutubeChannel).values(is_selected=False)
        )
        await session.execute(
            update(YoutubeChannel)
            .where(YoutubeChannel.id == channel_id)
            .values(is_selected=True)
        )
        await session.commit()

        channels = list((
            await session.execute(
                select(YoutubeChannel).order_by(YoutubeChannel.created_at)
            )
        ).scalars())

    return [
        ChannelOut(
            id=item.id,
            name=item.name,
            is_selected=item.is_selected,
        )
        for item in channels
    ]


@router.delete("/youtube/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: uuid.UUID):
    async with SessionLocal() as session:
        channel = await session.get(YoutubeChannel, channel_id)
        if channel is None:
            raise HTTPException(404, "channel not found")
        await session.delete(channel)
        await session.commit()


@router.post("/scripts/{script_id}/youtube", response_model=UploadOut, status_code=202)
async def upload_to_youtube(script_id: uuid.UUID, body: UploadIn):
    state = await deps.script_or_404(script_id)
    if state.final_video_status != "ready":
        raise HTTPException(
            409,
            "the final video is not ready (build it first, or rebuild it if it is outdated)",
        )

    async with SessionLocal() as session:
        channel = (
            await session.execute(
                select(YoutubeChannel).where(YoutubeChannel.is_selected.is_(True))
            )
        ).scalars().first()
        if channel is None:
            raise HTTPException(409, "no YouTube channel is selected")

        claimed = (
            await session.execute(
                update(State)
                .where(
                    State.id == script_id,
                    State.youtube_status != "uploading",
                )
                .values(
                    youtube_status="uploading",
                    youtube_url=None,
                    youtube_error=None,
                )
                .returning(State.id)
            )
        ).scalar_one_or_none()
        await session.commit()

    if claimed is None:
        raise HTTPException(409, "the video is already being uploaded")

    title = (body.title or state.generated_response_title or state.user_prompt).strip()[:100]
    metadata = {
        "title": title,
        "description": body.description,
        "tags": body.tags,
        "category_id": body.category_id,
        "privacy": body.privacy,
    }
    deps.spawn(_upload_job(script_id, channel.id, metadata))
    return UploadOut(status="uploading", url=None, error=None)


@router.get("/scripts/{script_id}/youtube", response_model=UploadOut)
async def get_youtube_upload(script_id: uuid.UUID):
    state = await deps.script_or_404(script_id)
    return UploadOut(
        status=state.youtube_status,
        url=state.youtube_url,
        error=state.youtube_error,
    )
