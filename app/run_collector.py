"""Standalone collector: `python -m app.run_collector` (for cron or a separate container).

Exits 0 on success and 1 if the run crashes (e.g. the database is unreachable), so the
scheduler (Render cron, crontab, ...) marks the run as failed. Individual feed errors are
logged and stored in feed_states.last_error but do not fail the run.
"""

import logging

from app import config
from app.collector import collect_all

logger = logging.getLogger(__name__)


def main() -> int:
    config.configure_logging()
    try:
        counts = collect_all()
    except Exception:
        logger.exception("collection failed")
        return 1
    logger.info("new articles: %d", sum(counts.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
