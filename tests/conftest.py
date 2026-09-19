import pytest

from app import main


@pytest.fixture(autouse=True)
def no_network_collect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "collect_all", lambda: {"nhk": 0})
