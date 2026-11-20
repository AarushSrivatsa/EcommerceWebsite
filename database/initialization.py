"""Database engine, sessions, and startup initialization."""
import asyncio

from sqlalchemy import inspect, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateColumn

from config import DATABASE_URL
from .models import Base, Section, State, EMBEDDING_DIM

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


def _sync_model_columns(connection) -> None:
    """Add model columns missing from existing tables, using SQLAlchemy model metadata."""
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue

        existing_columns = {
            column["name"] for column in inspector.get_columns(table.name)
        }
        for column in table.columns:
            if column.name in existing_columns or column.primary_key:
                continue

            definition = str(
                CreateColumn(column).compile(dialect=connection.dialect)
            )
            connection.exec_driver_sql(
                f'ALTER TABLE "{table.name}" ADD COLUMN {definition}'
            )


async def initialize_database() -> None:
    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(_sync_model_columns)

        # Keep stored embeddings compatible with the current model dimension.
        dimension = await connection.scalar(
            text(
                "SELECT atttypmod FROM pg_attribute "
                "WHERE attrelid = 'sections'::regclass AND attname = 'embedding'"
            )
        )
        if dimension is not None and dimension != EMBEDDING_DIM:
            await connection.execute(text("UPDATE sections SET embedding = NULL"))
            await connection.execute(
                text(
                    f"ALTER TABLE sections "
                    f"ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM})"
                )
            )

        await connection.execute(
            update(State)
            .where(State.generation_status == "generating")
            .values(
                generation_status="failed",
                generation_error="interrupted by a server restart",
            )
        )
        await connection.execute(
            update(State)
            .where(State.final_video_status == "processing")
            .values(
                final_video_status="failed",
                final_video_error="interrupted by a server restart",
            )
        )
        await connection.execute(
            update(State)
            .where(State.youtube_status == "uploading")
            .values(
                youtube_status="failed",
                youtube_error="interrupted by a server restart",
            )
        )
        await connection.execute(
            update(Section)
            .where(Section.video_status == "processing")
            .values(video_status="pending")
        )


if __name__ == "__main__":
    asyncio.run(initialize_database(), loop_factory=asyncio.SelectorEventLoop)
