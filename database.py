# db.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import DATABASE_URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import UUID, DateTime, func
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

class Base(DeclarativeBase):
    __abstract__ = True
    id : Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4,nullable=False)
    created_at : Mapped[datetime] = mapped_column(DateTime,server_default=func.now())
    updated_at : Mapped[datetime] = mapped_column(DateTime,server_default=func.now(),onupdate=lambda : datetime.now(timezone.utc))

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