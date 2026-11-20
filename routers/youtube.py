"""YouTube: store channel credentials, pick the channel, upload the final video to it."""
import asyncio
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import crypto
import database.database as db
import deps
import media.youtube_service as youtube_service

router = APIRouter(tags=["youtube"])


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)               # any name you like, e.g. the channel's name
    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)
    refresh_token: str = Field(min_length=1)                      # of the Google account that owns the channel


class ChannelOut(BaseModel):
    id: uuid.UUID
    name: str
    is_selected: bool


def channel_out(channel: db.YoutubeChannel) -> ChannelOut:
    return ChannelOut(id=channel.id, name=channel.name, is_selected=channel.is_selected)     # secrets never leave the server


@router.post("/youtube/channels", response_model=ChannelOut, status_code=201)
async def add_channel(body: ChannelCreate):
    """Checks the credentials with Google, then stores them encrypted. The first channel added is selected."""
    stored = {"client_id": body.client_id.strip(), "client_secret": body.client_secret.strip(),
              "token_uri": youtube_service.TOKEN_URI, "refresh_token": body.refresh_token.strip()}
    try:
        await asyncio.to_thread(youtube_service.check_credentials, stored)
    except Exception as exc:
        raise HTTPException(400, f"Google did not accept these credentials: {exc}")
    return channel_out(await db.add_channel(body.name, crypto.encrypt(stored)))


@router.get("/youtube/channels", response_model=list[ChannelOut])
async def list_channels():
    return [channel_out(channel) for channel in await db.list_channels()]


@router.post("/youtube/channels/{channel_id}/select", response_model=list[ChannelOut])
async def select_channel(channel_id: uuid.UUID):
    if not await db.select_channel(channel_id):
        raise HTTPException(404, "channel not found")
    return [channel_out(channel) for channel in await db.list_channels()]


@router.delete("/youtube/channels/{channel_id}", status_code=204)
async def delete_channel(channel_id: uuid.UUID):
    if not await db.delete_channel(channel_id):
        raise HTTPException(404, "channel not found")


class UploadIn(BaseModel):
    title: str | None = Field(default=None, max_length=100)       # default: the script's title
    description: str = Field(default="", max_length=5000)
    tags: list[str] = []
    category_id: str = "22"
    privacy: Literal["private", "unlisted", "public"] = "private"


class UploadOut(BaseModel):
    status: str                      # none | uploading | done | failed
    url: str | None
    error: str | None


def upload_out(state: db.State) -> UploadOut:
    return UploadOut(status=state.youtube_status, url=state.youtube_url, error=state.youtube_error)


@router.post("/scripts/{script_id}/youtube", response_model=UploadOut, status_code=202)
async def upload_to_youtube(script_id: uuid.UUID, body: UploadIn):
    """Uploads the final video to the selected channel. Runs in the background: poll GET /scripts/{id}/youtube."""
    state = await deps.script_or_404(script_id)
    if state.final_video_status != "ready":
        raise HTTPException(409, "the final video is not ready (build it first, or rebuild it if it is outdated)")
    channel = await db.get_selected_channel()
    if channel is None:
        raise HTTPException(409, "no YouTube channel is selected")
    if not await db.claim_youtube_upload(script_id):
        raise HTTPException(409, "the video is already being uploaded")
    title = (body.title or state.generated_response_title or state.user_prompt).strip()[:100]
    meta = {"title": title, "description": body.description, "tags": body.tags,
            "category_id": body.category_id, "privacy": body.privacy}
    deps.spawn(youtube_service.upload_job(script_id, channel.id, meta))
    return upload_out(await deps.script_or_404(script_id))


@router.get("/scripts/{script_id}/youtube", response_model=UploadOut)
async def get_youtube_upload(script_id: uuid.UUID):
    return upload_out(await deps.script_or_404(script_id))
