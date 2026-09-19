# jp-news-excerpt-api

FastAPI service that collects Japanese news from RSS feeds and stores only the title, a summary excerpt (max 300 chars), the link and the publish date. No full article bodies are stored or scraped; article pages are never fetched.

## API

| Endpoint | Description |
| --- | --- |
| `GET /health` | Liveness check |
| `GET /sources` | Configured source names |
| `GET /articles` | `source`, `q`, `since`, `limit` (1-100, default 20), `offset`; returns `{total, items}` |
| `GET /articles/{id}` | One article, 404 if missing |
| `POST /admin/collect` | Run a collection now; needs header `X-API-Key: $ADMIN_KEY` (always 403 if `ADMIN_KEY` is empty) |

Interactive docs: `/docs`.

## Configuration (environment variables)

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./news.db` | Postgres URLs starting with `postgres://` or `postgresql://` (e.g. from Neon) are rewritten to `postgresql+psycopg://`; query strings like `?sslmode=require` are kept |
| `COLLECT_INTERVAL_MINUTES` | `20` | Scheduler interval |
| `ENABLE_SCHEDULER` | `true` | `false` disables the in-process scheduler |
| `USER_AGENT` | placeholder | Set to something identifying you, with contact details |
| `SUMMARY_MAX_CHARS` | `300` | |
| `ADMIN_KEY` | empty | Empty disables `/admin/collect` |
| `LOG_LEVEL` | `INFO` | |

Feeds are listed in `FEEDS` in `app/config.py`. Check each site's robots.txt and terms before adding one.

## Run locally

    python3.12 -m venv .venv312 && source .venv312/bin/activate
    pip install -r requirements-dev.txt
    alembic upgrade head
    uvicorn app.main:app --reload

The schema is managed by Alembic; tables are not created automatically, so run `alembic upgrade head` first (and again after pulling new migrations).

Create a migration after changing `app/models.py`:

    alembic revision --autogenerate -m "describe change"

## Test

    pytest

Tests use temporary SQLite databases and mocked HTTP; they never touch the network.

## Collecting

Three ways, use one of them per deployment:

1. **In-process scheduler** (default): the app collects shortly after startup and every `COLLECT_INTERVAL_MINUTES`.
2. **Standalone entrypoint**, for cron or a separate container (set `ENABLE_SCHEDULER=false` on the API):

       python -m app.run_collector

   Example crontab (every 20 minutes): `*/20 * * * * cd /srv/app && python -m app.run_collector`.
3. **On demand**: `curl -X POST -H "X-API-Key: $ADMIN_KEY" http://localhost:8000/admin/collect`.

The scheduler lives inside each uvicorn process, so with `--workers N` (or several replicas) every process would collect. Set `ENABLE_SCHEDULER=false` there and run `app.run_collector` once from cron or a single container. Runs that race are safe (links are unique) but waste requests to the feeds.

Each run logs the number of new articles per source, e.g. `source=nhk new=12`; fetch failures are logged as warnings and stored in the `feed_states` table (`last_error`).

## Deploy with Docker

    docker compose up --build

This starts Postgres and the app on port 8000; the app runs `alembic upgrade head` before starting. Configure through the environment or a `.env` file next to `docker-compose.yml`:

    ADMIN_KEY=change-me
    USER_AGENT=my-news-app/1.0 (+https://example.com/contact)

`DATABASE_URL` is read from the environment (default points at the compose `db` service). To use an external Postgres, set `DATABASE_URL` and remove the `db` service.

Running the collector as its own container (with `ENABLE_SCHEDULER=false` on `app`):

    docker compose run --rm app python -m app.run_collector

Run that from the host's cron, or add a service with `command: python -m app.run_collector` on a schedule.

Multiple workers: `uvicorn app.main:app --workers 4` (with `ENABLE_SCHEDULER=false`). Migrations run once before the server starts; don't run `alembic upgrade head` from several replicas at the same moment.
