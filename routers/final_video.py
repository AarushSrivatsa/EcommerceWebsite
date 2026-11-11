"""The final video: stitch the per-section videos, check progress, delete."""
import uuid

from fastapi import APIRouter, HTTPException

import database as db
import deps
import storage
import video_service
from config import VIDEOS_BUCKET
from routers.scripts import FinalVideoOut, ScriptOut, script_out

router = APIRouter(tags=["final video"])


@router.post("/scripts/{script_id}/render_sections", response_model=ScriptOut, status_code=202)
async def render_sections(script_id: uuid.UUID):
    """Builds the video of every section that does not have an up-to-date one yet (not the final video).
    Runs in the background: poll GET /scripts/{id}/sections."""
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    if state.final_video_status == "processing":
        raise HTTPException(409, "the final video is being built")
    if await db.count_sections(script_id) == 0:
        raise HTTPException(409, "the script has no sections")
    deps.spawn(video_service.render_all_pending(script_id))
    return await script_out(state)


@router.post("/convert_into_video/{script_id}", response_model=ScriptOut, status_code=202)
async def convert_into_video(script_id: uuid.UUID):
    """Stitches the per-section videos into one video (rebuilding any section video that is out of date first).
    Runs in the background: poll GET /scripts/{id}/video until status is 'ready'."""
    state = await deps.script_or_404(script_id)
    if state.generation_status == "generating":
        raise HTTPException(409, "the script is still being written")
    if await db.count_sections(script_id) == 0:
        raise HTTPException(409, "the script has no sections")
    if not await db.claim_final_video(script_id):
        raise HTTPException(409, "the video is already being built")
    deps.spawn(video_service.convert_into_video(script_id))
    return await script_out(await deps.script_or_404(script_id))


@router.get("/scripts/{script_id}/video", response_model=FinalVideoOut)
async def get_final_video(script_id: uuid.UUID):
    return (await script_out(await deps.script_or_404(script_id))).final_video


@router.delete("/scripts/{script_id}/video", status_code=204)
async def delete_final_video(script_id: uuid.UUID):
    """Deletes the stitched video file (the section videos stay)."""
    state = await deps.script_or_404(script_id)
    if state.final_video_status == "processing":
        raise HTTPException(409, "the video is being built")
    old = await db.clear_final_video(script_id)
    await storage.delete_quiet(VIDEOS_BUCKET, [old])