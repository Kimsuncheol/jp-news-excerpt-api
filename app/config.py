import os

FEEDS: dict[str, str] = {
    "nhk": "https://news.web.nhk/n-data/conf/na/rss/cat0.xml",
}
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./news.db")
COLLECT_INTERVAL_MINUTES: int = int(os.getenv("COLLECT_INTERVAL_MINUTES", "20"))
USER_AGENT: str = os.getenv("USER_AGENT", "jp-news-excerpt-api/0.1 (+contact: set USER_AGENT)")
SUMMARY_MAX_CHARS: int = int(os.getenv("SUMMARY_MAX_CHARS", "300"))
ADMIN_KEY: str = os.getenv("ADMIN_KEY", "")
