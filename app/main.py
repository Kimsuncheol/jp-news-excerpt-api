import hmac
import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated

from apscheduler.schedulers.background import BackgroundScheduler
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app import config
from app.collector import collect_all
from app.db import get_db
from app.models import Article
from app.schemas import ArticleList, ArticleOut, CollectOut, ErrorOut

config.configure_logging()
logger = logging.getLogger(__name__)

STARTUP_DELAY_SECONDS = 10
_collect_lock = threading.Lock()


def run_collect() -> dict[str, int] | None:
    """Run collect_all unless a run is already in progress (returns None then)."""
    if not _collect_lock.acquire(blocking=False):
        return None
    try:
        return collect_all()
    finally:
        _collect_lock.release()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.scheduler = None
    if not config.ENABLE_SCHEDULER:
        logger.info("in-process scheduler disabled (ENABLE_SCHEDULER=false)")
        yield
        return
    scheduler = BackgroundScheduler(timezone=timezone.utc)
    scheduler.add_job(
        run_collect,
        "interval",
        minutes=config.COLLECT_INTERVAL_MINUTES,
        id="collect",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=STARTUP_DELAY_SECONDS),
    )
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("scheduler started, collecting every %d minutes", config.COLLECT_INTERVAL_MINUTES)
    try:
        yield
    finally:
        scheduler.shutdown(wait=True)


app = FastAPI(title="jp-news-excerpt-api", lifespan=lifespan)


# Static test page for trying the API in a browser: /test/
app.mount("/test", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="test-page")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@app.get("/sources", response_model=list[str])
def list_sources() -> list[str]:
    """Names of the configured feed sources."""
    return list(config.FEEDS)


@app.get("/articles", response_model=ArticleList)
def list_articles(
    db: Annotated[Session, Depends(get_db)],
    source: Annotated[str | None, Query(description="Only articles from this source")] = None,
    q: Annotated[str | None, Query(description="Case-insensitive substring match on title and summary")] = None,
    since: Annotated[
        datetime | None,
        Query(description="Only articles published at or after this time (naive values are treated as UTC)"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ArticleList:
    """List articles, newest first (articles without a publish date come last)."""
    filters = []
    if source:
        filters.append(Article.source == source)
    if q:
        pattern = f"%{escape_like(q)}%"
        filters.append(Article.title.ilike(pattern, escape="\\") | Article.summary.ilike(pattern, escape="\\"))
    if since:
        filters.append(Article.published_at >= (since if since.tzinfo else since.replace(tzinfo=timezone.utc)))

    total = db.scalar(select(func.count()).select_from(Article).where(*filters)) or 0
    items = db.scalars(
        select(Article)
        .where(*filters)
        .order_by(case((Article.published_at.is_(None), 1), else_=0), Article.published_at.desc(), Article.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ArticleList(total=total, items=[ArticleOut.model_validate(a) for a in items])


@app.get("/articles/{article_id}", response_model=ArticleOut, responses={404: {"model": ErrorOut}})
def get_article(article_id: int, db: Annotated[Session, Depends(get_db)]) -> Article:
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@app.post(
    "/admin/collect",
    response_model=CollectOut,
    responses={403: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def admin_collect(x_api_key: str | None = Header(default=None)) -> CollectOut:
    """Run a collection now. Requires the X-API-Key header to match ADMIN_KEY."""
    key = config.ADMIN_KEY
    if not key or x_api_key is None or not hmac.compare_digest(x_api_key.encode(), key.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")
    result = run_collect()
    if result is None:
        raise HTTPException(status_code=409, detail="Collection already running")
    return CollectOut(new_articles=result)
