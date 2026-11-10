# database.py
import asyncio
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import UUID, DateTime, ForeignKey, Integer, Float, Text, UniqueConstraint, func, select, text
from sqlalchemy import update as sql_update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from BaseState import BaseState
from config import DATABASE_URL, IMAGES_BUCKET, AUDIOS_BUCKET, VIDEOS_BUCKET

engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
    echo=False,
    connect_args={"sslmode": "require"},
)

SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


class Base(DeclarativeBase):
    __abstract__ = True
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class State(Base):
    __tablename__ = "states"

    # Basic information  (id comes from Base and is the BaseState id)
    user_prompt: Mapped[str] = mapped_column(Text)

    # generation details
    progress_context: Mapped[str | None] = mapped_column(Text)
    user_prompted_sectional_changes: Mapped[dict | None] = mapped_column(JSONB)   # {"1": "make it funnier"}
    sections_completed: Mapped[int | None] = mapped_column(Integer)
    video_type: Mapped[str | None] = mapped_column(Text)

    # generator manager
    router_prompt: Mapped[str | None] = mapped_column(Text)
    generator_response: Mapped[str | None] = mapped_column(Text)
    similarity_score: Mapped[float | None] = mapped_column(Float)
    similarity_threshold: Mapped[float | None] = mapped_column(Float)
    generated_response_title: Mapped[str | None] = mapped_column(Text)
    generated_response_word_count: Mapped[int | None] = mapped_column(Integer)

    # duration information
    estimated_duration_in_hours: Mapped[float] = mapped_column(Float)
    words_per_minute: Mapped[int] = mapped_column(Integer)
    total_sections: Mapped[int | None] = mapped_column(Integer)

    # router control
    next_step: Mapped[str | None] = mapped_column(Text)
    current_section: Mapped[int | None] = mapped_column(Integer)
    rewrite_attempts: Mapped[int] = mapped_column(Integer, default=0)
    section_word_limit_error_percentage: Mapped[float] = mapped_column(Float, default=10.0)

    voice_model: Mapped[str | None] = mapped_column(Text)
    current_node: Mapped[str | None] = mapped_column(Text)

    # script generation status (managed by the API, not by the graph)
    generation_status: Mapped[str] = mapped_column(Text, default="ready", server_default="ready")   # generating|ready|failed
    generation_error: Mapped[str | None] = mapped_column(Text)

    # the final stitched video (path inside the videos bucket)
    final_video_path: Mapped[str | None] = mapped_column(Text)
    final_video_status: Mapped[str] = mapped_column(Text, default="none", server_default="none")   # none|processing|ready|outdated|failed
    final_video_error: Mapped[str | None] = mapped_column(Text)


EMBEDDING_DIM = 384      # bge-small-en-v1.5; a pgvector column has a fixed length, so this must match nodes.EMBEDDING_MODEL


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("state_id", "position"),)

    state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("states.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    embedding = mapped_column(Vector(EMBEDDING_DIM))
    image_prompt: Mapped[str | None] = mapped_column(Text)    # suggested visual, written by the LLM

    # storage paths (inside the images / audios / videos buckets)
    image_path: Mapped[str | None] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(Text)
    video_path: Mapped[str | None] = mapped_column(Text)

    # video freshness: every change to text or image bumps content_rev, so a finished render can tell it is stale
    video_status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")   # pending|processing|ready|failed
    video_error: Mapped[str | None] = mapped_column(Text)
    content_rev: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


# ── graph persistence ─────────────────────────────────────────────────────────
async def save_state(state: BaseState, update: dict) -> None:
    """Save the state as it will look after this node's update (inserts the first time, updates after)."""
    values = state.model_copy(update=update).model_dump()
    async with SessionLocal() as session:
        await session.merge(State(**values))
        await session.commit()


async def load_section(state_id: uuid.UUID, position: int) -> str | None:
    """Text of one saved section (used to show the router what a rewrite starts from)."""
    async with SessionLocal() as session:
        stmt = select(Section.text).where(Section.state_id == state_id, Section.position == position)
        return (await session.execute(stmt)).scalar_one_or_none()


# ── scripts ───────────────────────────────────────────────────────────────────
async def get_state(state_id: uuid.UUID) -> State | None:
    async with SessionLocal() as session:
        return await session.get(State, state_id)


async def list_states(limit: int = 50, offset: int = 0) -> list[State]:
    async with SessionLocal() as session:
        stmt = select(State).order_by(State.created_at.desc()).limit(limit).offset(offset)
        return list((await session.execute(stmt)).scalars())


async def set_state_fields(state_id: uuid.UUID, **fields) -> None:
    async with SessionLocal() as session:
        await session.execute(sql_update(State).where(State.id == state_id).values(**fields))
        await session.commit()


async def claim_generation(state_id: uuid.UUID) -> bool:
    """Atomically mark the script as generating. False if it already is (so two jobs never run at once)."""
    stmt = (sql_update(State)
            .where(State.id == state_id, State.generation_status != "generating")
            .values(generation_status="generating", generation_error=None)
            .returning(State.id))
    async with SessionLocal() as session:
        claimed = (await session.execute(stmt)).scalar_one_or_none() is not None
        await session.commit()
    return claimed


async def claim_final_video(state_id: uuid.UUID) -> bool:
    stmt = (sql_update(State)
            .where(State.id == state_id, State.final_video_status != "processing")
            .values(final_video_status="processing", final_video_error=None)
            .returning(State.id))
    async with SessionLocal() as session:
        claimed = (await session.execute(stmt)).scalar_one_or_none() is not None
        await session.commit()
    return claimed


async def mark_final_outdated(state_id: uuid.UUID) -> None:
    """A section changed, so the stitched video no longer matches the script."""
    async with SessionLocal() as session:
        await session.execute(
            sql_update(State)
            .where(State.id == state_id, State.final_video_status == "ready")
            .values(final_video_status="outdated"))
        await session.commit()


async def finish_final_video(state_id: uuid.UUID, path: str, snapshot: list[tuple]) -> tuple[bool, str | None]:
    """Stores the stitched video. snapshot = [(section_id, content_rev)] used to build it; if any section changed
    meanwhile the video is saved as 'outdated'. Returns (applied, old_path_to_delete)."""
    async with SessionLocal() as session:
        async with session.begin():
            state = await session.get(State, state_id, with_for_update=True)
            if state is None:
                return False, None
            current = (await session.execute(
                select(Section.id, Section.content_rev).where(Section.state_id == state_id).order_by(Section.position)
            )).all()
            same = [tuple(row) for row in current] == [tuple(item) for item in snapshot]
            old = state.final_video_path
            state.final_video_path = path
            state.final_video_status = "ready" if same else "outdated"
            state.final_video_error = None
    return True, old


async def clear_final_video(state_id: uuid.UUID) -> str | None:
    async with SessionLocal() as session:
        async with session.begin():
            state = await session.get(State, state_id, with_for_update=True)
            if state is None:
                return None
            old = state.final_video_path
            state.final_video_path = None
            state.final_video_status = "none"
            state.final_video_error = None
    return old


async def delete_state(state_id: uuid.UUID) -> dict[str, list[str]] | None:
    """Deletes the script and its sections (FK cascade). Returns every storage path to remove, per bucket."""
    async with SessionLocal() as session:
        async with session.begin():
            state = await session.get(State, state_id)
            if state is None:
                return None
            sections = list((await session.execute(select(Section).where(Section.state_id == state_id))).scalars())
            files = {
                IMAGES_BUCKET: [s.image_path for s in sections if s.image_path],
                AUDIOS_BUCKET: [s.audio_path for s in sections if s.audio_path],
                VIDEOS_BUCKET: [s.video_path for s in sections if s.video_path],
            }
            if state.final_video_path:
                files[VIDEOS_BUCKET].append(state.final_video_path)
            await session.delete(state)
    return files


async def reset_interrupted_jobs() -> None:
    """Jobs that were running when the server stopped will never finish: unstick them."""
    async with SessionLocal() as session:
        await session.execute(sql_update(State).where(State.generation_status == "generating")
                              .values(generation_status="failed", generation_error="interrupted by a server restart"))
        await session.execute(sql_update(State).where(State.final_video_status == "processing")
                              .values(final_video_status="failed", final_video_error="interrupted by a server restart"))
        await session.execute(sql_update(Section).where(Section.video_status == "processing")
                              .values(video_status="pending"))
        await session.commit()


# ── sections ──────────────────────────────────────────────────────────────────
async def load_sections(state_id: uuid.UUID) -> list[Section]:
    """All saved sections of a script, in order."""
    async with SessionLocal() as session:
        stmt = select(Section).where(Section.state_id == state_id).order_by(Section.position)
        return list((await session.execute(stmt)).scalars())


async def get_section(state_id: uuid.UUID, position: int) -> Section | None:
    async with SessionLocal() as session:
        stmt = select(Section).where(Section.state_id == state_id, Section.position == position)
        return (await session.execute(stmt)).scalar_one_or_none()


async def get_section_by_id(section_id: uuid.UUID) -> Section | None:
    async with SessionLocal() as session:
        return await session.get(Section, section_id)


async def count_sections(state_id: uuid.UUID) -> int:
    async with SessionLocal() as session:
        stmt = select(func.count()).select_from(Section).where(Section.state_id == state_id)
        return (await session.execute(stmt)).scalar_one()


async def update_section_content(state_id: uuid.UUID, position: int, **fields) -> Section | None:
    """Changes the text and/or image of a section and marks its video as needing a re-render."""
    where = (Section.state_id == state_id, Section.position == position)
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                sql_update(Section).where(*where)
                .values(**fields, content_rev=Section.content_rev + 1, video_status="pending", video_error=None))
            return (await session.execute(select(Section).where(*where))).scalar_one_or_none()


async def mark_all_sections_changed(state_id: uuid.UUID) -> None:
    """Every video has to be rebuilt (e.g. the voice changed)."""
    async with SessionLocal() as session:
        await session.execute(
            sql_update(Section).where(Section.state_id == state_id)
            .values(content_rev=Section.content_rev + 1, video_status="pending", video_error=None))
        await session.commit()


async def _shift(session, state_id: uuid.UUID, from_position: int, delta: int) -> None:
    """Moves every section at or after from_position by delta. Goes through negative numbers so the
    unique (state_id, position) constraint is never hit halfway."""
    await session.execute(
        sql_update(Section).where(Section.state_id == state_id, Section.position >= from_position)
        .values(position=-(Section.position + delta)))
    await session.execute(
        sql_update(Section).where(Section.state_id == state_id, Section.position < 0)
        .values(position=-Section.position))


async def _sync_counts(session, state_id: uuid.UUID) -> None:
    count = (await session.execute(
        select(func.count()).select_from(Section).where(Section.state_id == state_id))).scalar_one()
    await session.execute(sql_update(State).where(State.id == state_id)
                          .values(total_sections=count, sections_completed=count))


async def insert_section(state_id: uuid.UUID, position: int, **values) -> Section:
    async with SessionLocal() as session:
        async with session.begin():
            await _shift(session, state_id, position, +1)
            section = Section(state_id=state_id, position=position, video_status="pending", content_rev=1, **values)
            session.add(section)
            await session.flush()
            await _sync_counts(session, state_id)
    return section


async def delete_section(state_id: uuid.UUID, position: int) -> Section | None:
    """Deletes one section and closes the gap. Returns the deleted row so its files can be removed."""
    async with SessionLocal() as session:
        async with session.begin():
            stmt = select(Section).where(Section.state_id == state_id, Section.position == position).with_for_update()
            section = (await session.execute(stmt)).scalar_one_or_none()
            if section is None:
                return None
            await session.delete(section)
            await session.flush()
            await _shift(session, state_id, position + 1, -1)
            await _sync_counts(session, state_id)
    return section


# ── video render bookkeeping (compare-and-set on content_rev) ─────────────────
async def set_section_processing(section_id: uuid.UUID, rev: int) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            sql_update(Section).where(Section.id == section_id, Section.content_rev == rev)
            .values(video_status="processing", video_error=None).returning(Section.id))
        ok = result.scalar_one_or_none() is not None
        await session.commit()
    return ok


async def finish_section_render(section_id: uuid.UUID, rev: int, audio_path: str, video_path: str):
    """Stores a finished render. Returns the old (audio_path, video_path) to delete, or None if the section
    changed (or was deleted) while rendering, in which case the caller must discard the new files."""
    async with SessionLocal() as session:
        async with session.begin():
            section = await session.get(Section, section_id, with_for_update=True)
            if section is None or section.content_rev != rev:
                return None
            old = (section.audio_path, section.video_path)
            section.audio_path, section.video_path = audio_path, video_path
            section.video_status, section.video_error = "ready", None
    return old


async def fail_section_render(section_id: uuid.UUID, rev: int, error: str) -> None:
    async with SessionLocal() as session:
        await session.execute(
            sql_update(Section).where(Section.id == section_id, Section.content_rev == rev)
            .values(video_status="failed", video_error=error))
        await session.commit()


# ── setup ─────────────────────────────────────────────────────────────────────
MIGRATIONS = [   # create_all does not add columns to existing tables
    "ALTER TABLE sections ADD COLUMN IF NOT EXISTS image_path TEXT",
    "ALTER TABLE sections ADD COLUMN IF NOT EXISTS audio_path TEXT",
    "ALTER TABLE sections ADD COLUMN IF NOT EXISTS video_path TEXT",
    "ALTER TABLE sections ADD COLUMN IF NOT EXISTS video_status TEXT NOT NULL DEFAULT 'pending'",
    "ALTER TABLE sections ADD COLUMN IF NOT EXISTS video_error TEXT",
    "ALTER TABLE sections ADD COLUMN IF NOT EXISTS content_rev INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE states ADD COLUMN IF NOT EXISTS generation_status TEXT NOT NULL DEFAULT 'ready'",
    "ALTER TABLE states ADD COLUMN IF NOT EXISTS generation_error TEXT",
    "ALTER TABLE states ADD COLUMN IF NOT EXISTS final_video_path TEXT",
    "ALTER TABLE states ADD COLUMN IF NOT EXISTS final_video_status TEXT NOT NULL DEFAULT 'none'",
    "ALTER TABLE states ADD COLUMN IF NOT EXISTS final_video_error TEXT",
]


async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        for statement in MIGRATIONS:
            await conn.execute(text(statement))

        # An older database has vector(768) from the bigger embedder. pgvector keeps the length in atttypmod.
        # The old vectors cannot be cast to the new length, so they are cleared (they only help to spot repeated
        # text while a script is being written; new sections get new ones).
        length = await conn.scalar(text(
            "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'sections'::regclass AND attname = 'embedding'"))
        if length != EMBEDDING_DIM:
            await conn.execute(text("UPDATE sections SET embedding = NULL"))
            await conn.execute(text(f"ALTER TABLE sections ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM})"))


if __name__ == "__main__":
    asyncio.run(init_db(), loop_factory=asyncio.SelectorEventLoop)
