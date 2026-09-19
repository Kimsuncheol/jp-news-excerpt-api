"""Standalone collector: `python -m app.run_collector` (for cron or a separate container)."""

import logging

from app import config
from app.collector import collect_all

logger = logging.getLogger(__name__)


def main() -> int:
    config.configure_logging()
    counts = collect_all()
    logger.info("new articles: %d", sum(counts.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
