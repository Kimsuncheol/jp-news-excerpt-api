import pytest
from apscheduler.schedulers.base import STATE_STOPPED
from fastapi.testclient import TestClient

from app import config, main


def post(client: TestClient, key: str | None) -> int:
    headers = {} if key is None else {"X-API-Key": key}
    return client.post("/admin/collect", headers=headers).status_code


def test_empty_admin_key_always_403(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ADMIN_KEY", "")
    with TestClient(main.app) as c:
        assert post(c, None) == 403
        assert post(c, "") == 403
        assert post(c, "anything") == 403


def test_admin_key_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ADMIN_KEY", "s3cret")
    with TestClient(main.app) as c:
        assert post(c, None) == 403
        assert post(c, "wrong") == 403
        assert c.post("/admin/collect", headers={"X-API-Key": "日本語".encode()}).status_code == 403
        resp = c.post("/admin/collect", headers={"X-API-Key": "s3cret"})
        assert resp.status_code == 200
        assert resp.json() == {"new_articles": {"nhk": 0}}


def test_overlapping_run_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ADMIN_KEY", "k")
    with TestClient(main.app) as c:
        assert main._collect_lock.acquire(blocking=False)
        try:
            assert post(c, "k") == 409
        finally:
            main._collect_lock.release()


def test_scheduler_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "COLLECT_INTERVAL_MINUTES", 7)
    with TestClient(main.app) as c:
        sched = c.app.state.scheduler
        assert sched.running and str(sched.timezone) == "UTC"
        job = sched.get_job("collect")
        assert job.max_instances == 1 and job.coalesce is True
        assert job.trigger.interval.total_seconds() == 7 * 60
        assert job.next_run_time is not None
    assert sched.state == STATE_STOPPED
