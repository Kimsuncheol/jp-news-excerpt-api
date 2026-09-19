from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import collector, config, main
from app.db import Base, get_db

FEED_URL = "https://feeds.example.test/rss.xml"

# Item A is repeated at the end: duplicate links inside one feed must be stored once.
ITEM_A = """<item>
<title>  東京で<b>大雪</b>　交通に影響 </title>
<link>https://news.example.test/a</link>
<description>&lt;p&gt;気象庁は&lt;a href="https://x.test"&gt;東京&lt;/a&gt;などで大雪&amp;amp;強風に注意。&lt;br/&gt;&lt;/p&gt;</description>
<pubDate>Sat, 03 Jan 2026 09:00:00 +0900</pubDate>
</item>"""
ITEM_B = f"""<item>
<title>長文のニュース</title>
<link>https://news.example.test/b</link>
<description>&lt;p&gt;{"あいうえお" * 200}&lt;/p&gt;</description>
<pubDate>Fri, 02 Jan 2026 12:00:00 +0900</pubDate>
</item>"""
ITEM_C = """<item>
<title>年始のあいさつ</title>
<link>https://news.example.test/c</link>
<description>新年おめでとうございます。</description>
<pubDate>Thu, 01 Jan 2026 00:00:00 +0000</pubDate>
</item>"""


def make_feed(*items: str, encoding: str = "utf-8") -> bytes:
    xml = f'<?xml version="1.0" encoding="{encoding}"?><rss version="2.0"><channel><title>テスト</title>{"".join(items)}</channel></rss>'
    return xml.encode(encoding)


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any request that is not served by an httpx.MockTransport fails the test."""

    def refuse(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"real network call attempted: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture(autouse=True)
def isolated_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lifespan tests must not fetch real feeds."""
    monkeypatch.setattr(main, "collect_all", lambda: {"nhk": 0})


@pytest.fixture
def sample_feed() -> bytes:
    return make_feed(ITEM_A, ITEM_B, ITEM_C, ITEM_A)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def mock_client() -> Callable[[Callable[[httpx.Request], httpx.Response]], httpx.Client]:
    return lambda handler: httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def api(engine: Engine, db: Session, mock_client: Callable[..., httpx.Client], monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """TestClient over a temp DB filled by collecting two mocked feeds ('nhk' and 'other')."""
    feeds = {
        "nhk": make_feed(ITEM_A, ITEM_B, ITEM_C),
        "other": make_feed(
            "<item><title>100% 達成</title><link>https://o.test/1</link><description>x</description>"
            "<pubDate>Sun, 04 Jan 2026 00:00:00 +0000</pubDate></item>",
            "<item><title>1000 達成</title><link>https://o.test/2</link><description>y</description></item>",
        ),
    }
    client = mock_client(lambda r: httpx.Response(200, content=feeds["nhk" if r.url.host == "nhk.test" else "other"]))
    for source, host in (("nhk", "nhk.test"), ("other", "other.test")):
        collector.collect_source(db, client, source, f"https://{host}/rss")

    factory = sessionmaker(engine, expire_on_commit=False)

    def override() -> Iterator[Session]:
        with factory() as session:
            yield session

    main.app.dependency_overrides[get_db] = override
    monkeypatch.setattr(config, "FEEDS", {"nhk": "https://nhk.test/rss", "other": "https://other.test/rss"})
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
