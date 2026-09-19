import hashlib
from datetime import datetime, timezone

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime


def hash_link(link: str) -> str:
    return hashlib.sha256(link.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Article(Base):
    """Only title, excerpt, link and publish date are stored; never article bodies."""

    __tablename__ = "articles"
    __table_args__ = (Index("ix_articles_source_published_at", "source", "published_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(Text)
    link_hash: Mapped[str] = mapped_column(String(64), unique=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class FeedState(Base):
    __tablename__ = "feed_states"

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    etag: Mapped[str | None] = mapped_column(String(255), default=None)
    last_modified: Mapped[str | None] = mapped_column(String(255), default=None)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
