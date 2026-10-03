# db.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import DATABASE_URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import UUID, DateTime, func, Text, Integer, Float
import uuid
from datetime import datetime, timezone

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

def get_db():
    session = SessionLocal()        
    try:
        yield session
        session.commit()      
    except Exception as e:
        session.rollback()    
        raise e              
    finally:
        session.close()  


class Base(DeclarativeBase):
    __abstract__ = True
    id : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4,nullable=False)
    created_at : Mapped[datetime] = mapped_column(DateTime,server_default=func.now())
    updated_at : Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),onupdate=lambda : datetime.now(timezone.utc))


class State(Base):
    __tablename__ = "states"

    main_prompt: Mapped[str] = mapped_column(Text)
    complete_context_of_whats_done: Mapped[str] = mapped_column(Text, default="")
    to_do_notes: Mapped[str] = mapped_column(Text, default="")
    current_decision: Mapped[str] = mapped_column(Text, default="")

    section_user_wants_changed: Mapped[int | None] = mapped_column(Integer)
    user_suggested_changes: Mapped[str | None] = mapped_column(Text)

    estimated_duration_in_hours: Mapped[float] = mapped_column(Float)
    words_per_minute: Mapped[int] = mapped_column(Integer)

    sections_completed: Mapped[int] = mapped_column(Integer, default=0)
    no_of_sections_total: Mapped[int | None] = mapped_column(Integer)

    max_turns_per_section: Mapped[int] = mapped_column(Integer, default=3)
    turns_per_current_section: Mapped[int] = mapped_column(Integer, default=0)

