from collections.abc import Iterator
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import collector
from app.db import Base
from app.models import Article, FeedState

URL = "https://example.com/rss.xml"


def rss(items: str, encoding: str = "utf-8") -> bytes:
    xml = f'<?xml version="1.0" encoding="{encoding}"?><rss version="2.0"><channel><title>x</title>{items}</channel></rss>'
    return xml.encode(encoding)


ITEM = """<item><title>  日本の　<b>ニュース</b> &amp; 天気 </title><link>https://example.com/1</link>
<description>&lt;p&gt;東京は&lt;br/&gt;晴れ。   明日も&amp;quot;晴れ&amp;quot;。&lt;/p&gt;</description>
<pubDate>Thu, 01 Jan 2026 09:00:00 +0900</pubDate></item>"""


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def client_for(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_collect_cleans_and_stores(db: Session) -> None:
    c = client_for(httpx.MockTransport(lambda r: httpx.Response(200, content=rss(ITEM), headers={"ETag": '"e1"', "Last-Modified": "Wed, 01 Jan 2026 00:00:00 GMT"})))
    assert collector.collect_source(db, c, "nhk", URL) == 1
    a = db.scalars(select(Article)).one()
    assert a.title == "日本の ニュース & 天気"
    assert a.summary == '東京は 晴れ。 明日も"晴れ"。'
    assert a.published_at == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    state = db.get(FeedState, "nhk")
    assert (state.etag, state.last_error) == ('"e1"', None)


def test_dedupe(db: Session) -> None:
    c = client_for(httpx.MockTransport(lambda r: httpx.Response(200, content=rss(ITEM + ITEM))))
    assert collector.collect_source(db, c, "nhk", URL) == 1
    assert collector.collect_source(db, c, "nhk", URL) == 0
    assert len(db.scalars(select(Article)).all()) == 1


def test_summary_truncated(db: Session) -> None:
    item = f"<item><title>t</title><link>https://e.com/2</link><description>{'あ' * 500}</description></item>"
    c = client_for(httpx.MockTransport(lambda r: httpx.Response(200, content=rss(item))))
    collector.collect_source(db, c, "nhk", URL)
    assert len(db.scalars(select(Article)).one().summary) == 300


def test_conditional_request_and_304(db: Session) -> None:
    seen: list[httpx.Headers] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.headers)
        if "if-none-match" in req.headers:
            return httpx.Response(304)
        return httpx.Response(200, content=rss(ITEM), headers={"ETag": '"e1"', "Last-Modified": "Wed, 01 Jan 2026 00:00:00 GMT"})

    c = client_for(httpx.MockTransport(handler))
    assert collector.collect_source(db, c, "nhk", URL) == 1
    assert collector.collect_source(db, c, "nhk", URL) == 0
    assert "if-none-match" not in seen[0]
    assert seen[1]["if-none-match"] == '"e1"'
    assert seen[1]["if-modified-since"] == "Wed, 01 Jan 2026 00:00:00 GMT"
    assert db.get(FeedState, "nhk").last_error is None


def test_http_error_recorded_not_raised(db: Session) -> None:
    c = client_for(httpx.MockTransport(lambda r: httpx.Response(503)))
    assert collector.collect_source(db, c, "nhk", URL) == 0
    assert "503" in (db.get(FeedState, "nhk").last_error or "")


def test_network_error_recorded(db: Session) -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    assert collector.collect_source(db, client_for(httpx.MockTransport(boom)), "nhk", URL) == 0
    assert "down" in (db.get(FeedState, "nhk").last_error or "")


def test_shift_jis_bytes_not_garbled(db: Session) -> None:
    c = client_for(httpx.MockTransport(lambda r: httpx.Response(200, content=rss(ITEM, "shift_jis"), headers={"Content-Type": "application/xml"})))
    collector.collect_source(db, c, "nhk", URL)
    assert db.scalars(select(Article)).one().title == "日本の ニュース & 天気"


def test_collect_all_uses_shared_client(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(collector, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(collector, "FEEDS", {"a": "https://a.test/rss", "b": "https://b.test/rss"})
    clients: list[httpx.Client] = []
    orig = collector.collect_source

    def spy(db: Session, client: httpx.Client, source: str, url: str) -> int:
        clients.append(client)
        return orig(db, client, source, url)

    monkeypatch.setattr(collector, "collect_source", spy)
    real_client = httpx.Client
    monkeypatch.setattr(
        collector.httpx, "Client",
        lambda **kw: real_client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=rss(ITEM.replace("/1", "/" + r.url.host)))), **kw),
    )
    assert collector.collect_all() == {"a": 1, "b": 1}
    assert clients[0] is clients[1]
    assert clients[0].headers["user-agent"] == collector.USER_AGENT
