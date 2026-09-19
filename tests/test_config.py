import pytest
from sqlalchemy import create_engine

from app.config import normalize_database_url
from app.db import engine_kwargs


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql://u:p@host:5432/db", "postgresql+psycopg://u:p@host:5432/db"),
        (
            "postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require",
            "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require",
        ),
        ("postgres://u:p@host/db?sslmode=require", "postgresql+psycopg://u:p@host/db?sslmode=require"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),  # already explicit
        ("sqlite:///./news.db", "sqlite:///./news.db"),
        ("sqlite://", "sqlite://"),
        ("  postgres://u:p@host/db \n", "postgresql+psycopg://u:p@host/db"),
    ],
)
def test_normalize_database_url(url: str, expected: str) -> None:
    assert normalize_database_url(url) == expected


def test_normalized_url_uses_psycopg_and_keeps_query() -> None:
    parsed = create_engine(normalize_database_url("postgres://u:p@h/db?sslmode=require")).url
    assert parsed.drivername == "postgresql+psycopg"
    assert parsed.query == {"sslmode": "require"}


def test_engine_kwargs() -> None:
    pg = engine_kwargs("postgresql+psycopg://u:p@h/db")
    assert pg == {"pool_pre_ping": True, "pool_size": 3, "max_overflow": 2, "pool_recycle": 300}
    assert engine_kwargs("sqlite:///./news.db") == {"connect_args": {"check_same_thread": False}}
    create_engine("postgresql+psycopg://u:p@h/db", **pg)  # accepted by SQLAlchemy without connecting
    create_engine("sqlite://", **engine_kwargs("sqlite://"))
