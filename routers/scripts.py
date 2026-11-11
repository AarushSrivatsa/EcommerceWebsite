"""Scripts: create (starts the LangGraph), list, get, update, resume, delete."""
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

import database as db
import deps
import storage
from BaseState import BaseState
from config import VIDEOS_BUCKET

router = APIRouter(prefix="/scripts", tags=["scripts"])


class FinalVideoOut(BaseModel):
    """Also used by the final_video router."""
    status: str                           # none | processing | ready | outdated | failed
    url: str | None
    error: str | None


class ScriptOut(BaseModel):
    """What every script endpoint returns (also used by the final_video router)."""
    id: uuid.UUID
    user_prompt: str
    video_type: str | None
    voice_model: str | None
    words_per_minute: int
    estimated_duration_in_hours: float
    total_sections: int | None
    sections_completed: int | None
    generation_status: str                # generating | ready | failed
    generation_error: str | None
    final_video: FinalVideoOut
    created_at: datetime | None
    updated_at: datetime | None


async def script_out(s: db.State) -> ScriptOut:
    """Database row -> ScriptOut."""
    return ScriptOut(
        id=s.id, user_prompt=s.user_prompt, video_type=s.video_type, voice_model=s.voice_model,
        words_per_minute=s.words_per_minute, estimated_duration_in_hours=s.estimated_duration_in_hours,
        total_sections=s.total_sections, sections_completed=s.sections_completed,
        generation_status=s.generation_status, generation_error=s.generation_error,
        final_video=FinalVideoOut(status=s.final_video_status, url=await storage.url(VIDEOS_BUCKET, s.final_video_path),
                                  error=s.final_video_error),
        created_at=s.created_at, updated_at=s.updated_at)


class ScriptCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "examples": [{
            "user_prompt": "Interesting facts about octopuses",
            "estimated_duration_in_hours": 0.05,
        }]
    })

    user_prompt: str = Field(min_length=3)
    estimated_duration_in_hours: float = Field(gt=0)
    words_per_minute: int = Field(default=150, ge=60, le=300)
    total_sections: int | None = Field(default=None, ge=1, le=200)     # None = the model decides
    voice_model: str = "af_heart"
    video_type: Literal["facts", "story"] | None = None
    similarity_threshold: float | None = Field(default=None, gt=0, le=1)


@router.post("", response_model=ScriptOut, status_code=202)
async def create_script(body: ScriptCreate):
    """Starts writing the sections in the background. Poll GET /scripts/{id} and GET /scripts/{id}/sections."""
    base = BaseState(
        user_prompt=body.user_prompt, estimated_duration_in_hours=body.estimated_duration_in_hours,
        words_per_minute=body.words_per_minute, total_sections=body.total_sections, voice_model=body.voice_model,
        video_type=body.video_type, similarity_threshold=body.similarity_threshold, sections_completed=0)
    await db.save_state(base, {})
    await db.set_state_fields(base.id, generation_status="generating", generation_error=None)
    deps.spawn(deps.generation_job(base))
    return await script_out(await deps.script_or_404(base.id))


@router.get("", response_model=list[ScriptOut])
async def list_scripts(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return [await script_out(s) for s in await db.list_states(limit, offset)]


@router.get("/{script_id}", response_model=ScriptOut)
async def get_script(script_id: uuid.UUID):
    return await script_out(await deps.script_or_404(script_id))


class ScriptUpdate(BaseModel):
    voice_model: str | None = None
    words_per_minute: int | None = Field(default=None, ge=60, le=300)


@router.patch("/{script_id}", response_model=ScriptOut)
async def update_script(script_id: uuid.UUID, body: ScriptUpdate):
    """Changing the voice or speaking speed makes every section video out of date (build them again when you are ready)."""
    state = await deps.script_or_404(script_id)
    changes = body.model_dump(exclude_none=True)
    changes = {k: v for k, v in changes.items() if getattr(state, k) != v}
    if changes:
        await db.set_state_fields(script_id, **changes)
        await db.mark_all_sections_changed(script_id)
        await db.mark_final_outdated(script_id)
    return await script_out(await deps.script_or_404(script_id))


@router.post("/{script_id}/generate", response_model=ScriptOut, status_code=202)
async def resume_generation(script_id: uuid.UUID):
    """Continue writing a script whose generation failed or was interrupted."""
    state = await deps.script_or_404(script_id)
    if not await db.claim_generation(script_id):
        raise HTTPException(409, "the script is already being generated")
    deps.spawn(deps.generation_job(deps.state_from_row(state)))
    return await script_out(await deps.script_or_404(script_id))


@router.delete("/{script_id}", status_code=204)
async def delete_script(script_id: uuid.UUID):
    """Deletes the script, its sections, and every image, audio and video file stored for it."""
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    files = await db.delete_state(script_id)
    if files:
        await deps.delete_files(files)