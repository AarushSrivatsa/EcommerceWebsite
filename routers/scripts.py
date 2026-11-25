"""Script creation, editing, generation and deletion routes."""
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update

import deps
import database.storage as storage
from aiagent.BaseState import BaseState
from aiagent.nodes import similarity_limit
from config import IMAGES_BUCKET, AUDIOS_BUCKET, VIDEOS_BUCKET
from database.initialization import SessionLocal
from database.models import Section, State

router = APIRouter(prefix="/scripts", tags=["scripts"])


class FinalVideoOut(BaseModel):
    status: str
    url: str | None
    error: str | None


class ScriptOut(BaseModel):
    id: uuid.UUID
    user_prompt: str
    video_type: str | None
    voice_model: str | None
    words_per_minute: int
    similarity_threshold: float
    research_status: str
    research_error: str | None
    estimated_duration_in_hours: float
    total_sections: int | None
    sections_completed: int | None
    generation_status: str
    generation_error: str | None
    final_video: FinalVideoOut
    created_at: datetime | None
    updated_at: datetime | None


async def script_out(state: State) -> ScriptOut:
    return ScriptOut(
        id=state.id,
        user_prompt=state.user_prompt,
        video_type=state.video_type,
        voice_model=state.voice_model,
        words_per_minute=state.words_per_minute,
        similarity_threshold=similarity_limit(deps.state_from_row(state)),
        research_status=state.research_status,
        research_error=state.research_error,
        estimated_duration_in_hours=state.estimated_duration_in_hours,
        total_sections=state.total_sections,
        sections_completed=state.sections_completed,
        generation_status=state.generation_status,
        generation_error=state.generation_error,
        final_video=FinalVideoOut(
            status=state.final_video_status,
            url=await storage.url(VIDEOS_BUCKET, state.final_video_path),
            error=state.final_video_error,
        ),
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


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
    total_sections: int | None = Field(default=None, ge=1, le=200)
    voice_model: str = "Zoey"
    video_type: Literal["facts", "story"] | None = None
    similarity_threshold: float | None = Field(default=None, ge=0.5, le=1)


@router.post("", response_model=ScriptOut, status_code=202)
async def create_script(body: ScriptCreate):
    base = BaseState(
        user_prompt=body.user_prompt,
        estimated_duration_in_hours=body.estimated_duration_in_hours,
        words_per_minute=body.words_per_minute,
        total_sections=body.total_sections,
        voice_model=body.voice_model,
        video_type=body.video_type,
        similarity_threshold=body.similarity_threshold,
        sections_completed=0,
    )
    async with SessionLocal() as session:
        session.add(State(**base.model_dump(), render_mode="image"))
        await session.flush()
        await session.execute(
            update(State)
            .where(State.id == base.id)
            .values(generation_status="generating", generation_error=None)
        )
        await session.commit()

    deps.spawn(deps.generation_job(base))
    return await script_out(await deps.script_or_404(base.id))


@router.get("", response_model=list[ScriptOut])
async def list_scripts(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    async with SessionLocal() as session:
        states = list((
            await session.execute(
                select(State).order_by(State.created_at.desc()).limit(limit).offset(offset)
            )
        ).scalars())
    return [await script_out(state) for state in states]


@router.get("/{script_id}", response_model=ScriptOut)
async def get_script(script_id: uuid.UUID):
    return await script_out(await deps.script_or_404(script_id))


class ScriptUpdate(BaseModel):
    voice_model: str | None = None
    words_per_minute: int | None = Field(default=None, ge=60, le=300)
    similarity_threshold: float | None = Field(default=None, ge=0.5, le=1)


@router.patch("/{script_id}", response_model=ScriptOut)
async def update_script(script_id: uuid.UUID, body: ScriptUpdate):
    state = await deps.script_or_404(script_id)
    requested = body.model_dump(exclude_unset=True)
    if state.generation_status == "generating" and "similarity_threshold" in requested:
        raise HTTPException(409, "the similarity limit cannot be changed while sections are being generated")
    changes = {
        key: value
        for key, value in body.model_dump(exclude_unset=True).items()
        if getattr(state, key) != value
    }
    render_changes = {"voice_model", "words_per_minute"} & changes.keys()

    if changes:
        async with SessionLocal() as session:
            await session.execute(
                update(State).where(State.id == script_id).values(**changes)
            )
            # A similarity threshold affects future writing only; it does not invalidate rendered media.
            if render_changes:
                section_changes = {
                    "content_rev": Section.content_rev + 1,
                    "video_status": "pending",
                    "video_error": None,
                }
                await session.execute(
                    update(Section)
                    .where(Section.state_id == script_id)
                    .values(**section_changes)
                )
                await session.execute(
                    update(State)
                    .where(State.id == script_id, State.final_video_status == "ready")
                    .values(final_video_status="outdated")
                )
            await session.commit()

    return await script_out(await deps.script_or_404(script_id))


@router.post("/{script_id}/generate", response_model=ScriptOut, status_code=202)
async def resume_generation(script_id: uuid.UUID):
    state = await deps.script_or_404(script_id)
    base = deps.state_from_row(state)
    async with SessionLocal() as session:
        claimed = (
            await session.execute(
                update(State)
                .where(State.id == script_id, State.generation_status != "generating")
                .values(generation_status="generating", generation_error=None)
                .returning(State.id)
            )
        ).scalar_one_or_none()
        await session.commit()

    if claimed is None:
        raise HTTPException(409, "the script is already being generated")

    deps.spawn(deps.generation_job(base))
    return await script_out(await deps.script_or_404(script_id))


@router.delete("/{script_id}", status_code=204)
async def delete_script(script_id: uuid.UUID):
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)

    async with SessionLocal() as session:
        current_state = await session.get(State, script_id)
        if current_state is None:
            raise HTTPException(404, "script not found")

        sections = list((
            await session.execute(
                select(Section).where(Section.state_id == script_id)
            )
        ).scalars())
        files = {
            IMAGES_BUCKET: [
                path
                for section in sections
                for path in [section.image_path, *[
                    beat.get("image_path") for beat in (section.visual_plan or [])
                ]]
                if path
            ],
            AUDIOS_BUCKET: [section.audio_path for section in sections if section.audio_path],
            VIDEOS_BUCKET: [section.video_path for section in sections if section.video_path],
        }
        if current_state.final_video_path:
            files[VIDEOS_BUCKET].append(current_state.final_video_path)

        await session.delete(current_state)
        await session.commit()

    for bucket, paths in files.items():
        await storage.delete_quiet(bucket, paths)
