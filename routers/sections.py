"""Sections: list, get, add your own, edit the text yourself, AI rewrite, re-render, delete."""
import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import database as db
import deps
import storage
from config import IMAGES_BUCKET, AUDIOS_BUCKET, VIDEOS_BUCKET

router = APIRouter(prefix="/scripts/{script_id}/sections", tags=["sections"])


class SectionOut(BaseModel):
    """What every section endpoint returns (also used by the images router)."""
    position: int
    text: str
    word_count: int
    image_prompt: str | None
    image_url: str | None
    audio_url: str | None
    video_url: str | None                 # last finished video (may be older than the text while video_status != ready)
    video_status: str                     # pending | processing | ready | failed
    video_error: str | None
    updated_at: datetime | None


async def section_out(s: db.Section) -> SectionOut:
    """Database row -> SectionOut (storage paths become urls)."""
    image, audio, video = await asyncio.gather(
        storage.url(IMAGES_BUCKET, s.image_path), storage.url(AUDIOS_BUCKET, s.audio_path),
        storage.url(VIDEOS_BUCKET, s.video_path))
    return SectionOut(position=s.position, text=s.text, word_count=s.word_count, image_prompt=s.image_prompt,
                      image_url=image, audio_url=audio, video_url=video, video_status=s.video_status,
                      video_error=s.video_error, updated_at=s.updated_at)


@router.get("", response_model=list[SectionOut])
async def list_sections(script_id: uuid.UUID):
    await deps.script_or_404(script_id)
    return [await section_out(s) for s in await db.load_sections(script_id)]


@router.get("/{position}", response_model=SectionOut)
async def get_section(script_id: uuid.UUID, position: int):
    return await section_out(await deps.section_or_404(script_id, position))


class SectionCreate(BaseModel):
    text: str = Field(min_length=1)
    position: int | None = Field(default=None, ge=1)     # default: add at the end


@router.post("", response_model=SectionOut, status_code=201)
async def add_section(script_id: uuid.UUID, body: SectionCreate, render: bool = True):
    """Add a section you wrote yourself (at the end, or at `position`, pushing the others down)."""
    from nodes import embed, suggest_image_prompt
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    count = await db.count_sections(script_id)
    position = body.position or count + 1
    if position > count + 1:
        raise HTTPException(422, f"position must be between 1 and {count + 1}")
    text = body.text.strip()
    embedding, image_prompt = await asyncio.gather(embed(text), suggest_image_prompt(text))
    section = await db.insert_section(script_id, position, text=text, word_count=len(text.split()),
                                      embedding=embedding, image_prompt=image_prompt)
    await deps.section_changed(script_id, section.id, render)
    return await section_out(section)


class SectionUpdate(BaseModel):
    text: str = Field(min_length=1)


@router.patch("/{position}", response_model=SectionOut)
async def edit_section(script_id: uuid.UUID, position: int, body: SectionUpdate, render: bool = True):
    """Write the section text yourself. Its video is rebuilt."""
    from nodes import embed, suggest_image_prompt
    await deps.section_or_404(script_id, position)
    text = body.text.strip()
    embedding, image_prompt = await asyncio.gather(embed(text), suggest_image_prompt(text))
    section = await db.update_section_content(script_id, position, text=text, word_count=len(text.split()),
                                              embedding=embedding, image_prompt=image_prompt)
    if section is None:
        raise HTTPException(404, f"section {position} not found")
    await deps.section_changed(script_id, section.id, render)
    return await section_out(section)


class RewriteIn(BaseModel):
    instruction: str = Field(min_length=1)               # "make it funnier", "shorter", ...


@router.post("/{position}/rewrite", response_model=SectionOut)
async def rewrite_section(script_id: uuid.UUID, position: int, body: RewriteIn, render: bool = True):
    """Have the LangGraph rewrite this one section from an instruction. Its video is rebuilt."""
    state = await deps.script_or_404(script_id)
    await deps.section_or_404(script_id, position)
    count = await db.count_sections(script_id)
    if not await db.claim_generation(script_id):
        raise HTTPException(409, "the script is being generated, try again when it is done")
    try:
        base = deps.state_from_row(
            state, user_prompted_sectional_changes={position: body.instruction.strip()},
            sections_completed=count, total_sections=count, generator_response=None, generated_response_title=None,
            generated_response_word_count=None, similarity_score=None, current_section=None, next_step=None,
            rewrite_attempts=0)
        await deps.run_graph(base)
    except Exception as exc:
        deps.log.exception("rewrite failed for %s section %s", script_id, position)
        await db.set_state_fields(script_id, generation_status="ready")
        raise HTTPException(502, f"rewrite failed: {type(exc).__name__}: {exc}")
    await db.set_state_fields(script_id, generation_status="ready")
    section = await deps.section_or_404(script_id, position)
    await deps.section_changed(script_id, section.id, render)
    return await section_out(section)


@router.post("/{position}/render", response_model=SectionOut, status_code=202)
async def rerender_section(script_id: uuid.UUID, position: int):
    """Force a rebuild of this section's video (e.g. after a failure)."""
    section = await deps.section_or_404(script_id, position)
    updated = await db.update_section_content(script_id, position)     # bumps the revision, status -> pending
    await deps.section_changed(script_id, section.id)
    return await section_out(updated)


@router.delete("/{position}", status_code=204)
async def delete_section(script_id: uuid.UUID, position: int):
    """Deletes the section and its image, audio and video files; later sections move up by one."""
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    section = await db.delete_section(script_id, position)
    if section is None:
        raise HTTPException(404, f"section {position} not found")
    await deps.delete_files({IMAGES_BUCKET: [section.image_path], AUDIOS_BUCKET: [section.audio_path],
                             VIDEOS_BUCKET: [section.video_path]})
    await db.mark_final_outdated(script_id)