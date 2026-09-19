from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import config, main
from app.db import Base, get_db
from app.models import Article, hash_link


def dt(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=timezone.utc)


def art(title: str, published: datetime | None, source: str = "nhk", summary: str = "") -> Article:
    link = f"https://example.com/{title}-{published}-{source}"
    return Article(source=source, title=title, summary=summary, link=link, link_hash=hash_link(link), published_at=published)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as s:
        s.add_all(
            [
                art("old", dt(1)),
                art("new", dt(3)),
                art("nodate1", None),
                art("nodate2", None),
                art("same-a", dt(2)),
                art("same-b", dt(2)),
                art("100% sure", dt(4), source="other"),
                art("1000 sure", dt(4), source="other"),
                art("a_b", dt(5), summary="Hello World"),
                art("axb", dt(5)),
                art("back\\slash", dt(6)),
            ]
        )
        s.commit()

    def override() -> Iterator[Session]:
        with factory() as session:
            yield session

    main.app.dependency_overrides[get_db] = override
    monkeypatch.setattr(config, "FEEDS", {"nhk": "u1", "other": "u2"})
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def titles(client: TestClient, **params: object) -> list[str]:
    resp = client.get("/articles", params=params)
    assert resp.status_code == 200
    return [a["title"] for a in resp.json()["items"]]


def test_sources(client: TestClient) -> None:
    assert client.get("/sources").json() == ["nhk", "other"]


def test_ordering_nulls_last_then_id_desc(client: TestClient) -> None:
    got = titles(client, limit=100)
    assert got[:2] == ["back\\slash", "axb"]  # published day 6, then day 5 (id desc)
    assert got[-2:] == ["nodate2", "nodate1"]  # nulls last, id desc
    assert got.index("same-b") < got.index("same-a")  # tie on published_at -> id desc


def test_total_and_paging(client: TestClient) -> None:
    body = client.get("/articles", params={"limit": 3, "offset": 2}).json()
    assert body["total"] == 11 and len(body["items"]) == 3
    assert titles(client, offset=100) == []


def test_source_and_since(client: TestClient) -> None:
    assert set(titles(client, source="other")) == {"100% sure", "1000 sure"}
    assert titles(client, since="2026-01-05T00:00:00Z", limit=100) == ["back\\slash", "axb", "a_b"]
    assert titles(client, since="2026-01-06T00:00:00", limit=100) == ["back\\slash"]  # naive = UTC


def test_q_escapes_wildcards(client: TestClient) -> None:
    assert titles(client, q="100%") == ["100% sure"]
    assert titles(client, q="a_b") == ["a_b"]
    assert titles(client, q="\\") == ["back\\slash"]
    assert titles(client, q="%") == ["100% sure"]
    assert titles(client, q="hello world") == ["a_b"]  # summary, case-insensitive


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"since": "nope"}])
def test_validation(client: TestClient, params: dict[str, object]) -> None:
    assert client.get("/articles", params=params).status_code == 422


def test_get_article(client: TestClient) -> None:
    first = client.get("/articles", params={"limit": 1}).json()["items"][0]
    resp = client.get(f"/articles/{first['id']}")
    assert resp.status_code == 200 and resp.json() == first
    missing = client.get("/articles/99999")
    assert missing.status_code == 404 and missing.json() == {"detail": "Article not found"}


def test_openapi(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    assert {"/health", "/sources", "/articles", "/articles/{article_id}", "/admin/collect"} <= set(paths)
    params = {p["name"]: p for p in paths["/articles"]["get"]["parameters"]}
    assert params["limit"]["schema"]["default"] == 20 and params["limit"]["schema"]["maximum"] == 100
    assert paths["/articles"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ArticleList"}
    assert "404" in paths["/articles/{article_id}"]["get"]["responses"]
    assert set(spec["components"]["schemas"]["ArticleList"]["properties"]) == {"total", "items"}
    assert client.get("/docs").status_code == 200
