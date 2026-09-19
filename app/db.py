from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, TypeDecorator, create_engine
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL



def engine_kwargs(url: str) -> dict[str, Any]:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    # Managed/free-tier Postgres closes idle connections: ping before use, recycle early, stay small.
    return {"pool_pre_ping": True, "pool_size": 3, "max_overflow": 2, "pool_recycle": 300}


engine = create_engine(DATABASE_URL, **engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes on every backend (SQLite drops tzinfo natively)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime not allowed; use timezone-aware values")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session

