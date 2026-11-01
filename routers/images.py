"""Section images: upload / replace and remove. Every change rebuilds that section's video."""
import mimetypes
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

import database as db
import deps
import storage
from config import IMAGES_BUCKET
from routers.sections import SectionOut, section_out

router = APIRouter(prefix="/scripts/{script_id}/sections/{position}/image", tags=["images"])

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024


@router.put("", response_model=SectionOut)
async def set_section_image(script_id: uuid.UUID, position: int, file: UploadFile = File(...)):
    """Upload (or replace) the image for a section. Its video is rebuilt with the new image."""
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
    await storage.upload_bytes(IMAGES_BUCKET, path, data, mimetypes.guess_type(path)[0] or "application/octet-stream")
    updated = await db.update_section_content(script_id, position, image_path=path)
    if updated is None:                                    # deleted while uploading
        await storage.delete_quiet(IMAGES_BUCKET, [path])
        raise HTTPException(404, f"section {position} not found")
    await storage.delete_quiet(IMAGES_BUCKET, [section.image_path])
    await deps.section_changed(script_id, updated.id)
    return await section_out(updated)


@router.delete("", response_model=SectionOut)
async def remove_section_image(script_id: uuid.UUID, position: int):
    """Remove the image (the video goes back to a plain dark card) and delete the file."""
    section = await deps.section_or_404(script_id, position)
    updated = await db.update_section_content(script_id, position, image_path=None)
    await storage.delete_quiet(IMAGES_BUCKET, [section.image_path])
    await deps.section_changed(script_id, updated.id)
    return await section_out(updated)