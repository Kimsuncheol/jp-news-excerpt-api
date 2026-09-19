import logging

import pytest

from app import run_collector


def test_main_runs_collect_all_and_logs(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(run_collector, "collect_all", lambda: {"nhk": 4, "other": 1})
    caplog.set_level(logging.INFO, logger="app.run_collector")
    assert run_collector.main() == 0
    assert "new articles: 5" in caplog.text
