"""SQLAlchemy ORM models shared by the application."""
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    UUID,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class State(Base):
    __tablename__ = "states"

    user_prompt: Mapped[str] = mapped_column(Text)

    progress_context: Mapped[str | None] = mapped_column(Text)
    user_prompted_sectional_changes: Mapped[dict | None] = mapped_column(JSONB)
    sections_completed: Mapped[int | None] = mapped_column(Integer)
    video_type: Mapped[str | None] = mapped_column(Text)
    render_mode: Mapped[str] = mapped_column(
        Text, default="image", server_default="image"
    )

    router_prompt: Mapped[str | None] = mapped_column(Text)
    generator_response: Mapped[str | None] = mapped_column(Text)
    similarity_score: Mapped[float | None] = mapped_column(Float)
    similarity_threshold: Mapped[float | None] = mapped_column(Float)
    generated_response_title: Mapped[str | None] = mapped_column(Text)
    generated_response_word_count: Mapped[int | None] = mapped_column(Integer)

    estimated_duration_in_hours: Mapped[float] = mapped_column(Float)
    words_per_minute: Mapped[int] = mapped_column(Integer)
    total_sections: Mapped[int | None] = mapped_column(Integer)

    next_step: Mapped[str | None] = mapped_column(Text)
    current_section: Mapped[int | None] = mapped_column(Integer)
    rewrite_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    section_word_limit_error_percentage: Mapped[float] = mapped_column(Float, default=10.0, server_default="10.0")

    voice_model: Mapped[str | None] = mapped_column(Text)
    current_node: Mapped[str | None] = mapped_column(Text)

    research_complete: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    research_status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending")
    research_error: Mapped[str | None] = mapped_column(Text)
    retrieved_sources: Mapped[list | None] = mapped_column(JSONB)
    visual_plan: Mapped[list | None] = mapped_column(JSONB)
    grounding_score: Mapped[float | None] = mapped_column(Float)
    grounding_feedback: Mapped[str | None] = mapped_column(Text)

    generation_status: Mapped[str] = mapped_column(
        Text, default="ready", server_default="ready"
    )
    generation_error: Mapped[str | None] = mapped_column(Text)

    final_video_path: Mapped[str | None] = mapped_column(Text)
    final_video_status: Mapped[str] = mapped_column(
        Text, default="none", server_default="none"
    )
    final_video_error: Mapped[str | None] = mapped_column(Text)

    youtube_status: Mapped[str] = mapped_column(
        Text, default="none", server_default="none"
    )
    youtube_url: Mapped[str | None] = mapped_column(Text)
    youtube_error: Mapped[str | None] = mapped_column(Text)


class YoutubeChannel(Base):
    __tablename__ = "youtube_channels"

    # Server defaults let SQLAlchemy add these columns to older existing tables.
    name: Mapped[str] = mapped_column(
        Text, default="YouTube channel", server_default="YouTube channel"
    )
    credentials: Mapped[str] = mapped_column(
        Text, default="", server_default=""
    )
    is_selected: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )


EMBEDDING_DIM = 384


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("state_id", "position"),)

    state_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("states.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    image_prompt: Mapped[str | None] = mapped_column(Text)
    sources: Mapped[list | None] = mapped_column(JSONB)
    visual_plan: Mapped[list | None] = mapped_column(JSONB)
    similarity_score: Mapped[float | None] = mapped_column(Float)
    similarity_threshold: Mapped[float | None] = mapped_column(Float)
    grounding_score: Mapped[float | None] = mapped_column(Float)
    grounding_feedback: Mapped[str | None] = mapped_column(Text)

    render_mode: Mapped[str] = mapped_column(
        Text, default="image", server_default="image"
    )
    image_path: Mapped[str | None] = mapped_column(Text)
    image_metadata: Mapped[dict | None] = mapped_column(JSONB)
    audio_path: Mapped[str | None] = mapped_column(Text)
    video_path: Mapped[str | None] = mapped_column(Text)
    credits_path: Mapped[str | None] = mapped_column(Text)
    subtitle_path: Mapped[str | None] = mapped_column(Text)

    video_status: Mapped[str] = mapped_column(
        Text, default="pending", server_default="pending"
    )
    video_error: Mapped[str | None] = mapped_column(Text)
    content_rev: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ResearchChunk(Base):
    """A source excerpt indexed for project-scoped semantic retrieval."""
    __tablename__ = "research_chunks"
    __table_args__ = (UniqueConstraint("state_id", "source_url", "chunk_index"),)

    state_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("states.id", ondelete="CASCADE"), index=True
    )
    source_url: Mapped[str] = mapped_column(Text)
    source_title: Mapped[str] = mapped_column(Text)
    source_domain: Mapped[str | None] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    content: Mapped[str] = mapped_column(Text)
    search_score: Mapped[float | None] = mapped_column(Float)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
