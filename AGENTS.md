# jp-news-excerpt-api

A FastAPI service that collects Japanese news from RSS feeds (NHK etc.), stores only the **title, a summary excerpt (max 300 chars), the link and the publish date**, and serves them via a REST API.

## Stack

- Python 3.12
- FastAPI
- SQLAlchemy 2.0 (sync sessions only, no async engine)
- httpx (feed fetching)
- feedparser (RSS parsing)
- APScheduler 3.x (periodic collection; do not upgrade to 4.x)
- pytest

## Data rules

- Store only: title, summary excerpt (truncated to at most 300 characters), link, publish date (plus source and internal ids/timestamps as needed).
- Never store or scrape full article bodies. Use only what the RSS feed provides, and never fetch the article page itself.
- Always link back to the original article.

## Legal / etiquette

- Respect robots.txt and each site's terms of use before adding or fetching a feed.
- Use an identifying User-Agent, sensible timeouts, and conservative polling intervals.
- If a site's terms forbid redistribution or automated collection, do not add it as a source.

## Code style

- Keep code minimal; don't add abstractions, layers or dependencies that aren't needed.
- Type-annotate all functions and use SQLAlchemy 2.0 style (`Mapped`, `mapped_column`, `select()`).
- Match the surrounding code's naming and comment density.

## Testing and completion

- Run `pytest` before declaring any task done, and report failures honestly.
- Tests must not hit the network; mock httpx and use fixture feed data.
- Add or update tests alongside behavior changes.
