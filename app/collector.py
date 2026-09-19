import html
import logging
import re
from calendar import timegm
from datetime import datetime, timezone
from time import struct_time

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import FEEDS, SUMMARY_MAX_CHARS, USER_AGENT
from app.db import SessionLocal
from app.models import Article, FeedState, hash_link, utcnow

logger = logging.getLogger(__name__)

BLOCK_TAG_RE = re.compile(r"</?(?:br|p|div|li|ul|ol|tr|h[1-6])\b[^>]*>", re.I)
TAG_RE = re.compile(r"<[^>]*>")
TITLE_MAX_CHARS = 500


def clean_text(raw: str) -> str:
    """Strip HTML tags, unescape entities and collapse whitespace.

    Block-level tags become a space; inline tags vanish so Japanese words are not split.
    """
    return " ".join(html.unescape(TAG_RE.sub("", BLOCK_TAG_RE.sub(" ", raw))).split())


def to_utc(t: struct_time | None) -> datetime | None:
    return datetime.fromtimestamp(timegm(t), timezone.utc) if t else None


def collect_source(db: Session, client: httpx.Client, source: str, url: str) -> int:
    """Fetch one feed with conditional requests and store new entries. Returns the number added."""
    state = db.get(FeedState, source) or FeedState(source=source)
    db.add(state)
    headers: dict[str, str] = {}
    if state.etag:
        headers["If-None-Match"] = state.etag
    if state.last_modified:
        headers["If-Modified-Since"] = state.last_modified

    state.last_checked_at = utcnow()
    try:
        resp = client.get(url, headers=headers)
        if resp.status_code == 304:
            state.last_error = None
            db.commit()
            logger.info("source=%s new=0 (not modified)", source)
            return 0
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        state.last_error = f"{type(exc).__name__}: {exc}"
        db.commit()
        logger.warning("source=%s fetch failed: %s", source, state.last_error)
        return 0

    feed = feedparser.parse(resp.content)
    if feed.bozo and not feed.entries:
        state.last_error = f"parse error: {feed.bozo_exception}"
        db.commit()
        logger.warning("source=%s %s", source, state.last_error)
        return 0

    candidates: dict[str, Article] = {}
    for entry in feed.entries:
        link = str(entry.get("link") or "").strip()
        if not link:
            continue
        link_hash = hash_link(link)
        candidates.setdefault(
            link_hash,
            Article(
                source=source,
                title=clean_text(str(entry.get("title", "")))[:TITLE_MAX_CHARS],
                summary=clean_text(str(entry.get("summary", "")))[:SUMMARY_MAX_CHARS],
                link=link,
                link_hash=link_hash,
                published_at=to_utc(entry.get("published_parsed") or entry.get("updated_parsed")),
            ),
        )

    existing: set[str] = set()
    if candidates:
        existing = set(db.scalars(select(Article.link_hash).where(Article.link_hash.in_(candidates))))
    new = [a for h, a in candidates.items() if h not in existing]
    db.add_all(new)

    state.etag = resp.headers.get("ETag")
    state.last_modified = resp.headers.get("Last-Modified")
    state.last_error = None
    try:
        db.commit()
    except IntegrityError:
        # Another process (cron, other worker) inserted the same links first; the next run sees them.
        db.rollback()
        logger.warning("source=%s concurrent insert detected, will retry on next run", source)
        return 0
    logger.info("source=%s new=%d", source, len(new))
    return len(new)


def collect_all() -> dict[str, int]:
    """Collect every feed in FEEDS with one shared client. Returns new-article counts per source."""
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=10, follow_redirects=True) as client:
        with SessionLocal() as db:
            counts = {source: collect_source(db, client, source, url) for source, url in FEEDS.items()}
    logger.info("collection finished: %s", ", ".join(f"{s}={n}" for s, n in counts.items()) or "no sources")
    return counts
