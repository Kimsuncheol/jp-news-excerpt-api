from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Article, FeedState, hash_link


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def make(link: str = "https://example.com/a", **kw: object) -> Article:
    return Article(source="nhk", title="t", summary="s", link=link, link_hash=hash_link(link), **kw)


def test_timezone_aware_roundtrip(session: Session) -> None:
    jst = timezone(timedelta(hours=9))
    session.add(make(published_at=datetime(2026, 1, 1, 9, 0, tzinfo=jst)))
    session.commit()
    session.expire_all()
    a = session.query(Article).one()
    assert a.published_at == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert a.published_at.tzinfo is not None and a.fetched_at.tzinfo is not None


def test_naive_datetime_rejected(session: Session) -> None:
    session.add(make(published_at=datetime(2026, 1, 1)))
    with pytest.raises(Exception):
        session.commit()


def test_link_hash_unique(session: Session) -> None:
    session.add(make())
    session.commit()
    session.add(make())
    with pytest.raises(IntegrityError):
        session.commit()


def test_indexes_and_feed_state(session: Session) -> None:
    idx = {i["name"]: i["column_names"] for i in inspect(session.bind).get_indexes("articles")}
    assert idx["ix_articles_source_published_at"] == ["source", "published_at"]
    session.add(FeedState(source="nhk"))
    session.commit()
    assert session.get(FeedState, "nhk").etag is None
