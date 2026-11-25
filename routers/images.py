"""Section image upload and deletion routes."""
import asyncio
import mimetypes
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from sqlalchemy import select, update

import deps
import database.storage as storage
from config import IMAGES_BUCKET
from database.initialization import SessionLocal
from database.models import Section, State
from routers.sections import SectionOut, section_out
from media.image_validation import validate_image_bytes
from media.cinematic_assets import search_and_download

router = APIRouter(prefix="/scripts/{script_id}/sections/{position}/image", tags=["images"])

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024


@router.put("", response_model=SectionOut)
async def set_section_image(
    script_id: uuid.UUID,
    position: int,
    file: UploadFile = File(...),
):
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    section = await deps.section_or_404(script_id, position)
    if section.video_status == "processing":
        raise HTTPException(409, "wait for the current scene render to finish before changing images")
    revision = section.content_rev
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(415, f"use one of: {', '.join(sorted(IMAGE_EXTENSIONS))}")

    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, f"image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(422, "empty file")
    try:
        validate_image_bytes(data, suffix)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    path = f"{script_id}/{section.id}-{uuid.uuid4().hex[:8]}{suffix}"
    await storage.upload_bytes(
        IMAGES_BUCKET,
        path,
        data,
        mimetypes.guess_type(path)[0] or "application/octet-stream",
    )

    old_path = None
    updated = None
    conflict = None
    async with SessionLocal() as session:
        async with session.begin():
            current = (
                await session.execute(
                    select(Section).where(Section.id == section.id).with_for_update()
                )
            ).scalar_one_or_none()
            if current is None:
                conflict = (404, f"section {position} not found")
            elif current.content_rev != revision:
                conflict = (409, "the section changed during upload; refresh and try again")
            else:
                old_path = current.image_path
                current.image_path = path
                current.image_metadata = {"origin": "user", "title": file.filename or "User image"}
                current.content_rev += 1
                current.video_status = "pending"
                current.video_error = None
                await session.execute(
                    update(State)
                    .where(State.id == script_id, State.final_video_status == "ready")
                    .values(final_video_status="outdated")
                )
                updated = current

    if conflict:
        await storage.delete_quiet(IMAGES_BUCKET, [path])
        raise HTTPException(*conflict)
    if old_path:
        await storage.delete_quiet(IMAGES_BUCKET, [old_path])
    return await section_out(updated)


@router.delete("", response_model=SectionOut)
async def remove_section_image(script_id: uuid.UUID, position: int):
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    section = await deps.section_or_404(script_id, position)
    if section.video_status == "processing":
        raise HTTPException(409, "wait for the current scene render to finish before changing images")
    revision = section.content_rev
    old_path = None
    updated = None
    conflict = None

    async with SessionLocal() as session:
        async with session.begin():
            current = (
                await session.execute(
                    select(Section).where(Section.id == section.id).with_for_update()
                )
            ).scalar_one_or_none()
            if current is None:
                conflict = (404, f"section {position} not found")
            elif current.content_rev != revision:
                conflict = (409, "the section changed; refresh and try again")
            else:
                old_path = current.image_path
                current.image_path = None
                current.image_metadata = None
                current.content_rev += 1
                current.video_status = "pending"
                current.video_error = None
                await session.execute(
                    update(State)
                    .where(State.id == script_id, State.final_video_status == "ready")
                    .values(final_video_status="outdated")
                )
                updated = current

    if conflict:
        raise HTTPException(*conflict)
    await storage.delete_quiet(IMAGES_BUCKET, [old_path])
    return await section_out(updated)



@router.post("/reroll", response_model=SectionOut)
async def reroll_section_image(script_id: uuid.UUID, position: int):
    """Replace a section image with another freely reusable Commons image."""
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    section = await deps.section_or_404(script_id, position)
    if section.video_status == "processing":
        raise HTTPException(409, "wait for the current section preview to finish before changing images")

    query = section.image_prompt or section.title or section.text[:180]
    previous_title = (section.image_metadata or {}).get("title")
    with tempfile.TemporaryDirectory(prefix="commons-reroll-") as temp_dir:
        asset = await asyncio.to_thread(
            search_and_download,
            query,
            Path(temp_dir),
            f"section-{position}-{uuid.uuid4().hex[:6]}",
            {previous_title} if previous_title else set(),
        )
        if not asset:
            raise HTTPException(
                404,
                "No different freely reusable image was found. Try again or upload your own image.",
            )
        local = Path(asset["path"])
        suffix = local.suffix.lower() or ".jpg"
        path = f"{script_id}/{section.id}-commons-{uuid.uuid4().hex[:10]}{suffix}"
        await storage.upload_file(
            IMAGES_BUCKET,
            path,
            local,
            mimetypes.guess_type(local.name)[0] or "image/jpeg",
        )

    old_path = None
    updated = None
    async with SessionLocal() as session:
        async with session.begin():
            current = (
                await session.execute(
                    select(Section).where(Section.id == section.id).with_for_update()
                )
            ).scalar_one_or_none()
            if current is None or current.content_rev != section.content_rev:
                await storage.delete_quiet(IMAGES_BUCKET, [path])
                raise HTTPException(409, "the section changed; refresh and try again")
            old_path = current.image_path
            current.image_path = path
            current.image_metadata = {
                "origin": "commons",
                "title": asset.get("title"),
                "credit": asset.get("credit"),
                "license": asset.get("license"),
                "license_url": asset.get("license_url"),
                "source_url": asset.get("source_url"),
                "query": asset.get("query") or query,
            }
            current.content_rev += 1
            current.video_status = "pending"
            current.video_error = None
            await session.execute(
                update(State)
                .where(State.id == script_id, State.final_video_status == "ready")
                .values(final_video_status="outdated")
            )
            updated = current

    if old_path and old_path != path:
        await storage.delete_quiet(IMAGES_BUCKET, [old_path])
    return await section_out(updated)
