# database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import DATABASE_URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import UUID, DateTime, UniqueConstraint, func, Text, Integer, Float, text
import uuid
from datetime import datetime
from sqlalchemy import ForeignKey
from pgvector.sqlalchemy import Vector
import asyncio
from sqlalchemy.dialects.postgresql import JSONB
from BaseState import BaseState

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
    id : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class State(Base):
    __tablename__ = "states"

    # Basic information  (id comes from Base and is the BaseState id)
    user_prompt: Mapped[str] = mapped_column(Text)

    # generation details
    progress_context: Mapped[str | None] = mapped_column(Text)
    user_prompted_sectional_changes: Mapped[list | None] = mapped_column(JSONB)
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

    # progress
    current_node: Mapped[str | None] = mapped_column(Text)

class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("state_id", "position"),)

    state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("states.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    embedding = mapped_column(Vector(768))

async def save_state(state: BaseState, update: dict) -> None:
    """Save the state as it will look after this node's update (inserts the first time, updates after)."""
    values = state.model_copy(update=update).model_dump()
    async with SessionLocal() as session:
        await session.merge(State(**values))
        await session.commit()

async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

if __name__ == "__main__":
    asyncio.run(init_db(), loop_factory=asyncio.SelectorEventLoop)