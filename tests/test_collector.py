from collections.abc import Callable
from datetime import datetime, timezone

import logging

import httpx
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import collector
from app.models import Article, FeedState
from tests.conftest import FEED_URL, ITEM_A, make_feed

MockClient = Callable[[Callable[[httpx.Request], httpx.Response]], httpx.Client]


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Article)) or 0


def articles(db: Session) -> dict[str, Article]:
    return {a.link.rsplit("/", 1)[-1]: a for a in db.scalars(select(Article))}


def test_first_collection_inserts_expected_articles(db: Session, mock_client: MockClient, sample_feed: bytes) -> None:
    client = mock_client(lambda r: httpx.Response(200, content=sample_feed))
    assert collector.collect_source(db, client, "nhk", FEED_URL) == 3
    got = articles(db)
    assert set(got) == {"a", "b", "c"}
    assert got["a"].title == "東京で大雪 交通に影響"
    assert got["a"].source == "nhk"
    assert got["a"].published_at == datetime(2026, 1, 3, 0, 0, tzinfo=timezone.utc)  # 09:00 JST
    assert got["c"].summary == "新年おめでとうございます。"
    assert db.get(FeedState, "nhk").last_error is None


def test_second_collection_with_304_inserts_nothing(db: Session, mock_client: MockClient, sample_feed: bytes) -> None:
    seen: list[httpx.Headers] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.headers)
        if req.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, content=sample_feed, headers={"ETag": '"v1"', "Last-Modified": "Sat, 03 Jan 2026 00:00:00 GMT"})

    client = mock_client(handler)
    assert collector.collect_source(db, client, "nhk", FEED_URL) == 3
    assert collector.collect_source(db, client, "nhk", FEED_URL) == 0
    assert "if-none-match" not in seen[0]
    assert seen[1]["if-none-match"] == '"v1"'
    assert seen[1]["if-modified-since"] == "Sat, 03 Jan 2026 00:00:00 GMT"
    assert count(db) == 3


def test_duplicate_links_never_reinserted(db: Session, mock_client: MockClient, sample_feed: bytes) -> None:
    client = mock_client(lambda r: httpx.Response(200, content=sample_feed))  # no ETag: full body each time
    assert collector.collect_source(db, client, "nhk", FEED_URL) == 3  # item A appears twice in the feed
    assert collector.collect_source(db, client, "nhk", FEED_URL) == 0
    assert count(db) == 3
    extra = make_feed(ITEM_A, "<item><title>新着</title><link>https://news.example.test/d</link></item>")
    client = mock_client(lambda r: httpx.Response(200, content=extra))
    assert collector.collect_source(db, client, "nhk", FEED_URL) == 1
    assert count(db) == 4


def test_html_stripped_and_summary_truncated(db: Session, mock_client: MockClient, sample_feed: bytes) -> None:
    collector.collect_source(db, mock_client(lambda r: httpx.Response(200, content=sample_feed)), "nhk", FEED_URL)
    got = articles(db)
    assert got["a"].summary == "気象庁は東京などで大雪&強風に注意。"
    assert len(got["b"].summary) == 300
    assert got["b"].summary == "あいうえお" * 60
    for a in got.values():
        assert "<" not in a.title + a.summary and ">" not in a.title + a.summary


def test_http_500_records_error_without_raising(db: Session, mock_client: MockClient) -> None:
    client = mock_client(lambda r: httpx.Response(500))
    assert collector.collect_source(db, client, "nhk", FEED_URL) == 0
    state = db.get(FeedState, "nhk")
    assert "500" in (state.last_error or "")
    assert state.last_checked_at is not None
    assert count(db) == 0


def test_network_error_records_error_and_success_clears_it(db: Session, mock_client: MockClient, sample_feed: bytes) -> None:
    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert collector.collect_source(db, mock_client(down), "nhk", FEED_URL) == 0
    assert "down" in (db.get(FeedState, "nhk").last_error or "")
    assert collector.collect_source(db, mock_client(lambda r: httpx.Response(200, content=sample_feed)), "nhk", FEED_URL) == 3
    assert db.get(FeedState, "nhk").last_error is None


def test_shift_jis_feed_not_garbled(db: Session, mock_client: MockClient) -> None:
    body = make_feed(ITEM_A, encoding="shift_jis")
    collector.collect_source(db, mock_client(lambda r: httpx.Response(200, content=body)), "nhk", FEED_URL)
    assert articles(db)["a"].title == "東京で大雪 交通に影響"


def test_collect_all_shares_one_client(monkeypatch: pytest.MonkeyPatch, engine: Engine, sample_feed: bytes) -> None:
    monkeypatch.setattr(collector, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(collector, "FEEDS", {"a": "https://a.test/rss", "b": "https://b.test/rss"})
    used: list[httpx.Client] = []
    orig = collector.collect_source
    monkeypatch.setattr(collector, "collect_source", lambda db, client, s, u: (used.append(client), orig(db, client, s, u))[1])
    real = httpx.Client
    monkeypatch.setattr(
        collector.httpx, "Client",
        lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=sample_feed.replace(b"/a<", f"/{r.url.host}<".encode()))), **kw),
    )
    # host b returns the same feed except item A's link, so only that one is new
    assert collector.collect_all() == {"a": 3, "b": 1}
    assert len(used) == 2 and used[0] is used[1]
    assert used[0].headers["user-agent"] == collector.USER_AGENT


def test_logs_new_count_per_source(db: Session, mock_client: MockClient, sample_feed: bytes, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="app.collector")
    client = mock_client(lambda r: httpx.Response(200, content=sample_feed))
    collector.collect_source(db, client, "nhk", FEED_URL)
    collector.collect_source(db, client, "nhk", FEED_URL)
    assert "source=nhk new=3" in caplog.text
    assert "source=nhk new=0" in caplog.text


def test_concurrent_insert_does_not_raise(db: Session, mock_client: MockClient, sample_feed: bytes) -> None:
    """Another process wins the race on the unique link_hash: the final commit fails once."""
    real_commit = db.commit
    calls = {"n": 0}

    def commit_once_failing() -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: articles.link_hash"))
        real_commit()

    db.commit = commit_once_failing  # type: ignore[method-assign]
    client = mock_client(lambda r: httpx.Response(200, content=sample_feed))
    assert collector.collect_source(db, client, "nhk", FEED_URL) == 0
    assert count(db) == 0
    assert collector.collect_source(db, client, "nhk", FEED_URL) == 3  # picked up on the next run
