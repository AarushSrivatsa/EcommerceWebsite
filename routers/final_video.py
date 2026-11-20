"""Routes for building, checking and deleting the final stitched video."""
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select, update

import deps
import database.storage as storage
import media.video_service as video_service
from config import VIDEOS_BUCKET
from database.initialization import SessionLocal
from database.models import Section, State
from routers.scripts import FinalVideoOut, ScriptOut, script_out

router = APIRouter(tags=["final video"])


@router.post("/scripts/{script_id}/render_sections", response_model=ScriptOut, status_code=202)
async def render_sections(script_id: uuid.UUID):
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    if state.final_video_status == "processing":
        raise HTTPException(409, "the final video is being built")

    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(Section).where(Section.state_id == script_id)
        )
    if not count:
        raise HTTPException(409, "the script has no sections")

    deps.spawn(video_service.render_all_pending(script_id))
    return await script_out(state)


@router.post("/convert_into_video/{script_id}", response_model=ScriptOut, status_code=202)
async def convert_into_video(script_id: uuid.UUID):
    state = await deps.script_or_404(script_id)
    if state.generation_status == "generating":
        raise HTTPException(409, "the script is still being written")

    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(Section).where(Section.state_id == script_id)
        )
        claimed = (
            await session.execute(
                update(State)
                .where(
                    State.id == script_id,
                    State.final_video_status != "processing",
                )
                .values(final_video_status="processing", final_video_error=None)
                .returning(State.id)
            )
        ).scalar_one_or_none()
        await session.commit()

    if not count:
        raise HTTPException(409, "the script has no sections")
    if claimed is None:
        raise HTTPException(409, "the video is already being built")

    deps.spawn(video_service.convert_into_video(script_id))
    return await script_out(await deps.script_or_404(script_id))


@router.get("/scripts/{script_id}/video", response_model=FinalVideoOut)
async def get_final_video(script_id: uuid.UUID):
    return (await script_out(await deps.script_or_404(script_id))).final_video


@router.delete("/scripts/{script_id}/video", status_code=204)
async def delete_final_video(script_id: uuid.UUID):
    state = await deps.script_or_404(script_id)
    if state.final_video_status == "processing":
        raise HTTPException(409, "the video is being built")

    async with SessionLocal() as session:
        await session.execute(
            update(State)
            .where(State.id == script_id)
            .values(
                final_video_path=None,
                final_video_status="none",
                final_video_error=None,
            )
        )
        await session.commit()

    await storage.delete_quiet(VIDEOS_BUCKET, [state.final_video_path])
