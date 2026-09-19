# jp-news-excerpt-api

FastAPI service that collects Japanese news from RSS feeds and stores only the title, a summary excerpt (max 300 chars), the link and the publish date. No full article bodies are stored or scraped.

## Run

    python3.12 -m venv .venv312 && source .venv312/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --reload

## Configuration (environment variables)

`DATABASE_URL` (default `sqlite:///./news.db`), `COLLECT_INTERVAL_MINUTES` (20), `USER_AGENT`, `SUMMARY_MAX_CHARS` (300), `ADMIN_KEY`. Feeds are listed in `app/config.py`.

## Test

    pytest
