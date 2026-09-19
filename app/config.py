import logging
import os

FEEDS: dict[str, str] = {
    "nhk": "https://news.web.nhk/n-data/conf/na/rss/cat0.xml",
}


def normalize_database_url(url: str) -> str:
    """Point plain Postgres URLs (as given by Neon, Heroku, ...) at the psycopg v3 driver."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


DATABASE_URL: str = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///./news.db"))
COLLECT_INTERVAL_MINUTES: int = int(os.getenv("COLLECT_INTERVAL_MINUTES", "20"))
USER_AGENT: str = os.getenv("USER_AGENT", "jp-news-excerpt-api/0.1 (+contact: set USER_AGENT)")
SUMMARY_MAX_CHARS: int = int(os.getenv("SUMMARY_MAX_CHARS", "300"))
ADMIN_KEY: str = os.getenv("ADMIN_KEY", "")
ENABLE_SCHEDULER: bool = os.getenv("ENABLE_SCHEDULER", "true").strip().lower() in {"1", "true", "yes", "on"}
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()


def configure_logging() -> None:
    logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
