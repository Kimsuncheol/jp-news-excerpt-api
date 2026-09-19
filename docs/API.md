# News Excerpt API: Frontend Guide

REST API serving Japanese news **excerpts** collected from RSS feeds (NHK etc.). Each article has only a title, a short summary (max 300 chars), the original link and the publish date. There is no article body: link users to `link` to read the full story.

- **Base URL:** `http://localhost:8000` locally, `https://<your-service>.onrender.com` when deployed (referred to as `BASE` below)
- **Format:** JSON, UTF-8. All endpoints below are `GET`, need no authentication and are read-only.
- **Live docs:** `BASE/docs` (Swagger UI) and `BASE/openapi.json` (generate a typed client from it if you like).
- **Try it:** `BASE/test/` is a small working example page.

## Things to know first

- **CORS is not enabled.** A browser app served from a different origin than the API will be blocked. Either serve the frontend from the same origin or through a proxy, or ask the backend to add `CORSMiddleware` with your origin.
- **Cold starts:** on the free Render plan the API sleeps after 15 minutes idle; the first request can take about a minute. Show a loading state and use a generous timeout.
- **Times are UTC** ISO 8601 strings ending in `Z`. Convert to the user's zone (JST for most readers) in the UI.
- **`published_at` can be `null`** (some feed items have no date). Handle it in the UI; such articles sort last.
- **Text is plain text.** HTML is stripped by the backend, but still render with `textContent`/normal JSX escaping, never as raw HTML.

## Types

```ts
interface Article {
  id: number;
  source: string;          // e.g. "nhk"
  title: string;           // max 500 chars
  summary: string;         // max 300 chars, may be empty
  link: string;            // URL of the original article
  published_at: string | null; // "2026-01-03T00:00:00Z"
}

interface ArticleList {
  total: number;           // all matches, ignoring limit/offset
  items: Article[];
}

interface ErrorBody { detail: string }
```

## Endpoints

### `GET /health`

Liveness check. `200` → `{ "status": "ok" }`.

### `GET /sources`

Names of the available sources, useful for a filter dropdown.

```json
["nhk"]
```

### `GET /articles`

List articles, newest first (`published_at` descending, then `id` descending; articles without a date come last).

| Query param | Type | Default | Description |
| --- | --- | --- | --- |
| `source` | string | none | Only this source (a name from `/sources`). Unknown names return an empty list. |
| `q` | string | none | Case-insensitive substring match on title **and** summary. `%` and `_` are treated literally. |
| `since` | ISO 8601 datetime | none | Only articles published at or after this time. A value without a timezone is treated as UTC. Articles without a date are excluded. |
| `limit` | integer 1-100 | `20` | Page size. |
| `offset` | integer >= 0 | `0` | Number of items to skip. |

Response `200` (`ArticleList`):

```json
{
  "total": 1,
  "items": [
    {
      "id": 1,
      "source": "nhk",
      "title": "東京で大雪 交通に影響",
      "summary": "気象庁は東京などで大雪に注意するよう呼びかけています。",
      "link": "https://www3.nhk.or.jp/news/html/20260103/k10000000001000.html",
      "published_at": "2026-01-03T00:00:00Z"
    }
  ]
}
```

Errors: `422` if a parameter is invalid (see below).

**Pagination:** use `total` with `limit`/`offset`. Next page: `offset += limit`; there is a next page while `offset + items.length < total`. `total` can change between requests when new articles arrive, so expect the occasional duplicate or skipped item when paging through a live feed.

### `GET /articles/{id}`

One article (`Article`). `404` with `{ "detail": "Article not found" }` if it does not exist; `422` if `id` is not an integer.

## Errors

| Status | When | Body |
| --- | --- | --- |
| `404` | Article id not found | `{ "detail": "Article not found" }` |
| `422` | Invalid query/path parameter | `{ "detail": [ { "type", "loc", "msg", "input" } ] }` |
| `5xx` | Server or database problem | may not be JSON; treat as generic failure |

Example `422` for `GET /articles?limit=500`:

```json
{
  "detail": [
    {
      "type": "less_than_equal",
      "loc": ["query", "limit"],
      "msg": "Input should be less than or equal to 100",
      "input": "500",
      "ctx": { "le": 100 }
    }
  ]
}
```

Note that `detail` is a string for `404`/`403`/`409` but an array for `422`.

## Example: fetch helper

```ts
const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function listArticles(opts: {
  source?: string; q?: string; since?: Date; limit?: number; offset?: number;
} = {}): Promise<ArticleList> {
  const params = new URLSearchParams();          // encodes Japanese text and "+" for you
  if (opts.source) params.set("source", opts.source);
  if (opts.q) params.set("q", opts.q);
  if (opts.since) params.set("since", opts.since.toISOString());
  params.set("limit", String(opts.limit ?? 20));
  params.set("offset", String(opts.offset ?? 0));

  const res = await fetch(`${BASE}/articles?${params}`, { signal: AbortSignal.timeout(70_000) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
```

Always build query strings with `URLSearchParams` (or `encodeURIComponent`): `since=2026-01-03T00:00:00+09:00` breaks if the `+` is not encoded.

## Not for the frontend

`POST /admin/collect` triggers a collection and requires the secret `X-API-Key` header. It is for operators and schedulers. **Never put that key in frontend code.** Without a valid key it returns `403 { "detail": "Forbidden" }`.

## Attribution

Articles belong to their publishers. Show the source name, link back to the original via `link`, and do not present the excerpt as the full article.
