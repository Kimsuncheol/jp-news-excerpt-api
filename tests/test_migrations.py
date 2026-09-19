from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parent.parent


def alembic_cfg(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_upgrade_matches_models_and_downgrades(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    cfg = alembic_cfg(url)
    command.upgrade(cfg, "head")
    insp = inspect(create_engine(url))
    assert {"articles", "feed_states"} <= set(insp.get_table_names())
    idx = {i["name"]: i["column_names"] for i in insp.get_indexes("articles")}
    assert idx["ix_articles_source_published_at"] == ["source", "published_at"]
    command.check(cfg)  # raises if models drift from the migration
    command.downgrade(cfg, "base")
    assert set(inspect(create_engine(url)).get_table_names()) == {"alembic_version"}
