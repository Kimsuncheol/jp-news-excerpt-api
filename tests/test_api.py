import pytest
from fastapi.testclient import TestClient

from app import config


def titles(api: TestClient, **params: object) -> list[str]:
    resp = api.get("/articles", params=params)
    assert resp.status_code == 200
    return [a["title"] for a in resp.json()["items"]]


def test_sources(api: TestClient) -> None:
    assert api.get("/sources").json() == ["nhk", "other"]


def test_filter_by_source(api: TestClient) -> None:
    assert api.get("/articles", params={"source": "nhk"}).json()["total"] == 3
    assert titles(api, source="other") == ["100% 達成", "1000 達成"]
    assert titles(api, source="nope") == []


def test_filter_by_q(api: TestClient) -> None:
    assert titles(api, q="大雪") == ["東京で大雪 交通に影響"]
    assert titles(api, q="新年") == ["年始のあいさつ"]  # matches summary
    assert titles(api, q="100%") == ["100% 達成"]  # % is literal, not a wildcard
    assert titles(api, q="%") == ["100% 達成"]
    assert titles(api, q="存在しない") == []


def test_filter_by_since(api: TestClient) -> None:
    assert titles(api, since="2026-01-03T00:00:00Z") == ["100% 達成", "東京で大雪 交通に影響"]
    assert titles(api, since="2026-01-03T00:00:01Z") == ["100% 達成"]
    assert titles(api, since="2026-02-01T00:00:00Z") == []


def test_pagination_and_ordering(api: TestClient) -> None:
    everything = titles(api, limit=100)
    assert everything == ["100% 達成", "東京で大雪 交通に影響", "長文のニュース", "年始のあいさつ", "1000 達成"]  # undated last
    body = api.get("/articles", params={"limit": 2}).json()
    assert body["total"] == 5 and len(body["items"]) == 2
    assert titles(api, limit=2, offset=2) == everything[2:4]
    assert titles(api, limit=2, offset=4) == everything[4:]
    assert titles(api, offset=50) == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_pagination_bounds(api: TestClient, params: dict[str, int]) -> None:
    assert api.get("/articles", params=params).status_code == 422


def test_article_detail_and_404(api: TestClient) -> None:
    first = api.get("/articles", params={"limit": 1}).json()["items"][0]
    assert api.get(f"/articles/{first['id']}").json() == first
    resp = api.get("/articles/999999")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Article not found"}


def test_admin_collect_requires_valid_key(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ADMIN_KEY", "s3cret")
    assert api.post("/admin/collect").status_code == 403
    assert api.post("/admin/collect", headers={"X-API-Key": "wrong"}).status_code == 403
    assert api.post("/admin/collect", headers={"X-API-Key": "s3cret"}).status_code == 200


def test_admin_collect_403_when_key_unset(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ADMIN_KEY", "")
    assert api.post("/admin/collect").status_code == 403
    assert api.post("/admin/collect", headers={"X-API-Key": ""}).status_code == 403
