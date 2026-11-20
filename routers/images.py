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

router = APIRouter(prefix="/scripts/{script_id}/sections/{position}/image", tags=["images"])

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024


@router.put("", response_model=SectionOut)
async def set_section_image(
    script_id: uuid.UUID,
    position: int,
    file: UploadFile = File(...),
):
    section = await deps.section_or_404(script_id, position)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(415, f"use one of: {', '.join(sorted(IMAGE_EXTENSIONS))}")

    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, f"image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(422, "empty file")

    path = f"{script_id}/{section.id}-{uuid.uuid4().hex[:8]}{suffix}"
    await storage.upload_bytes(
        IMAGES_BUCKET,
        path,
        data,
        mimetypes.guess_type(path)[0] or "application/octet-stream",
    )

    async with SessionLocal() as session:
        await session.execute(
            update(Section)
            .where(Section.id == section.id)
            .values(
                image_path=path,
                content_rev=Section.content_rev + 1,
                video_status="pending",
                video_error=None,
            )
        )
        await session.execute(
            update(State)
            .where(State.id == script_id, State.final_video_status == "ready")
            .values(final_video_status="outdated")
        )
        await session.commit()
        updated = await session.get(Section, section.id)

    if updated is None:
        await storage.delete_quiet(IMAGES_BUCKET, [path])
        raise HTTPException(404, f"section {position} not found")

    await storage.delete_quiet(IMAGES_BUCKET, [section.image_path])
    return await section_out(updated)


@router.delete("", response_model=SectionOut)
async def remove_section_image(script_id: uuid.UUID, position: int):
    section = await deps.section_or_404(script_id, position)

    async with SessionLocal() as session:
        await session.execute(
            update(Section)
            .where(Section.id == section.id)
            .values(
                image_path=None,
                content_rev=Section.content_rev + 1,
                video_status="pending",
                video_error=None,
            )
        )
        await session.execute(
            update(State)
            .where(State.id == script_id, State.final_video_status == "ready")
            .values(final_video_status="outdated")
        )
        await session.commit()
        updated = await session.get(Section, section.id)

    await storage.delete_quiet(IMAGES_BUCKET, [section.image_path])
    return await section_out(updated)



@router.put("/beats/{beat_index}", response_model=SectionOut)
async def set_visual_beat_image(
    script_id: uuid.UUID,
    position: int,
    beat_index: int,
    file: UploadFile = File(...),
):
    """Attach one image to one narration paragraph/visual beat (zero-based index)."""
    section = await deps.section_or_404(script_id, position)
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

    path = f"{script_id}/{section.id}-beat-{beat_index}-{uuid.uuid4().hex[:8]}{suffix}"
    await storage.upload_bytes(
        IMAGES_BUCKET,
        path,
        data,
        mimetypes.guess_type(path)[0] or "application/octet-stream",
    )

    old_path = None
    async with SessionLocal() as session:
        async with session.begin():
            current = (
                await session.execute(
                    select(Section)
                    .where(Section.id == section.id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if current is None:
                await storage.delete_quiet(IMAGES_BUCKET, [path])
                raise HTTPException(404, f"section {position} not found")
            current_plan = list(current.visual_plan or [])
            if beat_index >= len(current_plan):
                await storage.delete_quiet(IMAGES_BUCKET, [path])
                raise HTTPException(409, "the visual plan changed; refresh the section and try again")
            replaced_path = current_plan[beat_index].get("image_path")
            current_plan[beat_index] = {**current_plan[beat_index], "image_path": path}
            current.visual_plan = current_plan
            current.content_rev += 1
            current.video_status = "pending"
            current.video_error = None

            await session.execute(
                update(State)
                .where(State.id == script_id, State.final_video_status == "ready")
                .values(final_video_status="outdated")
            )
        updated = await session.get(Section, section.id)

    if replaced_path and replaced_path != path:
        await storage.delete_quiet(IMAGES_BUCKET, [replaced_path])
    if updated is None:
        raise HTTPException(404, f"section {position} not found")
    return await section_out(updated)


@router.delete("/beats/{beat_index}", response_model=SectionOut)
async def remove_visual_beat_image(
    script_id: uuid.UUID,
    position: int,
    beat_index: int,
):
    """Remove a custom beat image; the section image or neutral card becomes its fallback."""
    section = await deps.section_or_404(script_id, position)
    plan = list(section.visual_plan or [])
    if beat_index < 0 or beat_index >= len(plan):
        raise HTTPException(422, f"visual beat index must be between 0 and {len(plan) - 1}")

    old_path = None
    async with SessionLocal() as session:
        async with session.begin():
            current = (
                await session.execute(
                    select(Section)
                    .where(Section.id == section.id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if current is None:
                raise HTTPException(404, f"section {position} not found")
            current_plan = list(current.visual_plan or [])
            if beat_index >= len(current_plan):
                raise HTTPException(409, "the visual plan changed; refresh the section and try again")
            old_path = current_plan[beat_index].get("image_path")
            current_plan[beat_index] = {
                key: value for key, value in current_plan[beat_index].items()
                if key not in {"image_path", "image_url"}
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
        updated = await session.get(Section, section.id)

    await storage.delete_quiet(IMAGES_BUCKET, [old_path])
    if updated is None:
        raise HTTPException(404, f"section {position} not found")
    return await section_out(updated)
