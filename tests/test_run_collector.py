import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app import collector, run_collector
from app.models import Article
from tests.conftest import make_feed, ITEM_A, ITEM_B

ROOT = Path(__file__).resolve().parent.parent


def test_main_success_exits_0_and_logs(engine: Engine, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(collector, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(collector, "FEEDS", {"nhk": "https://feeds.example.test/rss.xml"})
    real = httpx.Client
    body = make_feed(ITEM_A, ITEM_B)
    monkeypatch.setattr(collector.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)), **kw))
    caplog.set_level(logging.INFO)
    assert run_collector.main() == 0
    assert "source=nhk new=2" in caplog.text and "new articles: 2" in caplog.text
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Article)) == 2


def test_main_returns_1_when_collection_crashes(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def boom() -> dict[str, int]:
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(run_collector, "collect_all", boom)
    assert run_collector.main() == 1
    assert "collection failed" in caplog.text


def test_module_exits_nonzero_when_database_unreachable() -> None:
    """Real `python -m app.run_collector` process pointed at a closed Postgres port."""
    env = {**os.environ, "DATABASE_URL": "postgres://u:p@127.0.0.1:1/db?connect_timeout=2"}
    proc = subprocess.run([sys.executable, "-m", "app.run_collector"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 1
    assert "collection failed" in proc.stderr
