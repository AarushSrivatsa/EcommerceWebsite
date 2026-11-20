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

    if updated is None:
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
