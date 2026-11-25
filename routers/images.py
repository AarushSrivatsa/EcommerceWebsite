"""Section image upload and deletion routes."""
import mimetypes
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
    if state.render_mode != "image":
        raise HTTPException(409, "Cinematic Skill finds its own visuals. No image upload is needed.")
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


@router.put("/beats/{beat_index}", response_model=SectionOut)
async def set_visual_beat_image(
    script_id: uuid.UUID,
    position: int,
    beat_index: int,
    file: UploadFile = File(...),
):
    """Attach one image to one narration paragraph/visual beat (zero-based index)."""
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    if state.render_mode != "image":
        raise HTTPException(409, "Cinematic Skill finds its own visuals. Manual image uploads are disabled.")
    section = await deps.section_or_404(script_id, position)
    if section.video_status == "processing":
        raise HTTPException(409, "wait for the current scene render to finish before changing images")
    revision = section.content_rev
    plan = list(section.visual_plan or [])
    if beat_index < 0 or beat_index >= len(plan):
        raise HTTPException(422, f"visual beat index must be between 0 and {len(plan) - 1}")

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

    path = f"{script_id}/{section.id}-beat-{beat_index}-{uuid.uuid4().hex[:8]}{suffix}"
    await storage.upload_bytes(
        IMAGES_BUCKET,
        path,
        data,
        mimetypes.guess_type(path)[0] or "application/octet-stream",
    )

    replaced_path = None
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
                current_plan = list(current.visual_plan or [])
                if beat_index >= len(current_plan):
                    conflict = (409, "the visual plan changed; refresh and try again")
                else:
                    replaced_path = current_plan[beat_index].get("image_path")
                    current_plan[beat_index] = {
                        **{
                            key: value for key, value in current_plan[beat_index].items()
                            if key not in {
                                "image_title", "image_credit", "image_license",
                                "image_license_url", "image_source_url", "image_date",
                                "image_description", "image_origin",
                            }
                        },
                        "image_path": path,
                        "image_origin": "user",
                    }
                    current.visual_plan = current_plan
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
    if replaced_path:
        await storage.delete_quiet(IMAGES_BUCKET, [replaced_path])
    return await section_out(updated)


@router.delete("/beats/{beat_index}", response_model=SectionOut)
async def remove_visual_beat_image(
    script_id: uuid.UUID,
    position: int,
    beat_index: int,
):
    """Remove a custom beat image; the section image or neutral card becomes its fallback."""
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    section = await deps.section_or_404(script_id, position)
    if section.video_status == "processing":
        raise HTTPException(409, "wait for the current scene render to finish before changing images")
    revision = section.content_rev
    plan = list(section.visual_plan or [])
    if beat_index < 0 or beat_index >= len(plan):
        raise HTTPException(422, f"visual beat index must be between 0 and {len(plan) - 1}")

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
                current_plan = list(current.visual_plan or [])
                if beat_index >= len(current_plan):
                    conflict = (409, "the visual plan changed; refresh the section and try again")
                else:
                    old_path = current_plan[beat_index].get("image_path")
                    current_plan[beat_index] = {
                        key: value
                        for key, value in current_plan[beat_index].items()
                        if key not in {"image_path", "image_url", "image_title", "image_credit", "image_license", "image_license_url", "image_source_url", "image_date", "image_description", "image_origin"}
                    }
                    current.visual_plan = current_plan
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
