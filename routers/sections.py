"""Section listing, editing, rendering and deletion routes."""
import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

import deps
import database.storage as storage
import media.video_service as video_service
from config import IMAGES_BUCKET, AUDIOS_BUCKET, VIDEOS_BUCKET
from database.initialization import SessionLocal
from database.models import Section, State

router = APIRouter(prefix="/scripts/{script_id}/sections", tags=["sections"])


class SectionOut(BaseModel):
    position: int
    text: str
    word_count: int
    image_prompt: str | None
    image_url: str | None
    audio_url: str | None
    video_url: str | None
    video_status: str
    video_error: str | None
    updated_at: datetime | None
    sources: list[dict] = []
    visual_plan: list[dict] = []
    similarity_score: float | None = None
    similarity_threshold: float | None = None
    grounding_score: float | None = None
    grounding_feedback: str | None = None


async def section_out(section: Section) -> SectionOut:
    image_url, audio_url, video_url = await asyncio.gather(
        storage.url(IMAGES_BUCKET, section.image_path),
        storage.url(AUDIOS_BUCKET, section.audio_path),
        storage.url(VIDEOS_BUCKET, section.video_path),
    )
    return SectionOut(
        position=section.position,
        text=section.text,
        word_count=section.word_count,
        image_prompt=section.image_prompt,
        image_url=image_url,
        audio_url=audio_url,
        video_url=video_url,
        video_status=section.video_status,
        video_error=section.video_error,
        updated_at=section.updated_at,
        sources=section.sources or [],
        visual_plan=section.visual_plan or [],
        similarity_score=section.similarity_score,
        similarity_threshold=section.similarity_threshold,
        grounding_score=section.grounding_score,
        grounding_feedback=section.grounding_feedback,
    )


@router.get("", response_model=list[SectionOut])
async def list_sections(script_id: uuid.UUID):
    await deps.script_or_404(script_id)
    async with SessionLocal() as session:
        sections = list((
            await session.execute(
                select(Section)
                .where(Section.state_id == script_id)
                .order_by(Section.position)
            )
        ).scalars())
    return [await section_out(section) for section in sections]


@router.get("/{position}", response_model=SectionOut)
async def get_section(script_id: uuid.UUID, position: int):
    return await section_out(await deps.section_or_404(script_id, position))


class SectionCreate(BaseModel):
    text: str = Field(min_length=1)
    position: int | None = Field(default=None, ge=1)


@router.post("", response_model=SectionOut, status_code=201)
async def add_section(script_id: uuid.UUID, body: SectionCreate):
    from aiagent.nodes import embed, suggest_image_prompt, similarity_limit

    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    text = body.text.strip()
    embedding, image_prompt = await asyncio.gather(
        embed(text), suggest_image_prompt(text)
    )

    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(Section).where(Section.state_id == script_id)
        )
        position = body.position or count + 1
        if position > count + 1:
            raise HTTPException(422, f"position must be between 1 and {count + 1}")

        # Shift through negative positions to avoid the unique (state_id, position) constraint.
        await session.execute(
            update(Section)
            .where(Section.state_id == script_id, Section.position >= position)
            .values(position=-(Section.position + 1))
        )
        await session.execute(
            update(Section)
            .where(Section.state_id == script_id, Section.position < 0)
            .values(position=-Section.position)
        )

        distance = Section.embedding.cosine_distance(embedding)
        nearest = await session.scalar(
            select(func.min(distance)).where(Section.state_id == script_id)
        )
        section = Section(
            state_id=script_id,
            position=position,
            text=text,
            word_count=len(text.split()),
            embedding=embedding,
            image_prompt=image_prompt,
            similarity_score=None if nearest is None else float(1 - nearest),
            similarity_threshold=similarity_limit(deps.state_from_row(state)),
            sources=[],
            visual_plan=[],
            video_status="pending",
            content_rev=1,
        )
        session.add(section)
        await session.flush()
        new_count = count + 1
        await session.execute(
            update(State)
            .where(State.id == script_id)
            .values(total_sections=new_count, sections_completed=new_count)
        )
        await session.execute(
            update(State)
            .where(State.id == script_id, State.final_video_status == "ready")
            .values(final_video_status="outdated")
        )
        await session.commit()
        await session.refresh(section)

    return await section_out(section)


class SectionUpdate(BaseModel):
    text: str = Field(min_length=1)


@router.patch("/{position}", response_model=SectionOut)
async def edit_section(script_id: uuid.UUID, position: int, body: SectionUpdate):
    from aiagent.nodes import embed, suggest_image_prompt, similarity_limit

    await deps.section_or_404(script_id, position)
    text = body.text.strip()
    embedding, image_prompt = await asyncio.gather(
        embed(text), suggest_image_prompt(text)
    )

    async with SessionLocal() as session:
        await session.execute(
            update(Section)
            .where(Section.state_id == script_id, Section.position == position)
            .values(
                text=text,
                word_count=len(text.split()),
                embedding=embedding,
                image_prompt=image_prompt,
                sources=[],
                visual_plan=[],
                similarity_score=None,
                similarity_threshold=similarity_limit(deps.state_from_row(await deps.script_or_404(script_id))),
                grounding_score=None,
                grounding_feedback=None,
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
        section = (
            await session.execute(
                select(Section).where(
                    Section.state_id == script_id,
                    Section.position == position,
                )
            )
        ).scalar_one_or_none()

    if section is None:
        raise HTTPException(404, f"section {position} not found")
    return await section_out(section)


class RewriteIn(BaseModel):
    instruction: str = Field(min_length=1)


@router.post("/{position}/rewrite", response_model=SectionOut)
async def rewrite_section(script_id: uuid.UUID, position: int, body: RewriteIn):
    state = await deps.script_or_404(script_id)
    await deps.section_or_404(script_id, position)

    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(Section).where(Section.state_id == script_id)
        )
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
        raise HTTPException(409, "the script is being generated, try again when it is done")

    try:
        base = deps.state_from_row(
            state,
            user_prompted_sectional_changes={position: body.instruction.strip()},
            sections_completed=count,
            total_sections=count,
            generator_response=None,
            generated_response_title=None,
            generated_response_word_count=None,
            similarity_score=None,
            current_section=None,
            next_step=None,
            rewrite_attempts=0,
        )
        await deps.run_graph(base)
    except Exception as exc:
        deps.log.exception("rewrite failed for %s section %s", script_id, position)
        async with SessionLocal() as session:
            await session.execute(
                update(State)
                .where(State.id == script_id)
                .values(generation_status="ready")
            )
            await session.commit()
        raise HTTPException(502, f"rewrite failed: {type(exc).__name__}: {exc}")

    async with SessionLocal() as session:
        await session.execute(
            update(State)
            .where(State.id == script_id)
            .values(generation_status="ready")
        )
        await session.execute(
            update(State)
            .where(State.id == script_id, State.final_video_status == "ready")
            .values(final_video_status="outdated")
        )
        await session.commit()
        section = (
            await session.execute(
                select(Section).where(
                    Section.state_id == script_id,
                    Section.position == position,
                )
            )
        ).scalar_one_or_none()

    if section is None:
        raise HTTPException(404, f"section {position} not found")
    return await section_out(section)


@router.post("/{position}/render", response_model=SectionOut, status_code=202)
async def render_section(script_id: uuid.UUID, position: int):
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)
    section = await deps.section_or_404(script_id, position)
    if section.video_status == "processing":
        raise HTTPException(409, "this section's video is already being built")

    async with SessionLocal() as session:
        await session.execute(
            update(Section)
            .where(Section.id == section.id)
            .values(
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

    deps.spawn(video_service.render_section_video(section.id))
    return await section_out(updated)


@router.delete("/{position}", status_code=204)
async def delete_section(script_id: uuid.UUID, position: int):
    state = await deps.script_or_404(script_id)
    deps.require_idle(state)

    async with SessionLocal() as session:
        section = (
            await session.execute(
                select(Section)
                .where(
                    Section.state_id == script_id,
                    Section.position == position,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if section is None:
            raise HTTPException(404, f"section {position} not found")

        image_path, audio_path, video_path = (
            section.image_path, section.audio_path, section.video_path
        )
        await session.delete(section)
        await session.flush()

        # Close the position gap without colliding with the unique constraint.
        await session.execute(
            update(Section)
            .where(Section.state_id == script_id, Section.position >= position + 1)
            .values(position=-(Section.position - 1))
        )
        await session.execute(
            update(Section)
            .where(Section.state_id == script_id, Section.position < 0)
            .values(position=-Section.position)
        )

        count = await session.scalar(
            select(func.count()).select_from(Section).where(Section.state_id == script_id)
        )
        await session.execute(
            update(State)
            .where(State.id == script_id)
            .values(
                total_sections=count,
                sections_completed=count,
                final_video_status=(
                    "outdated" if state.final_video_status == "ready"
                    else state.final_video_status
                ),
            )
        )
        await session.commit()

    await storage.delete_quiet(IMAGES_BUCKET, [image_path])
    await storage.delete_quiet(AUDIOS_BUCKET, [audio_path])
    await storage.delete_quiet(VIDEOS_BUCKET, [video_path])
