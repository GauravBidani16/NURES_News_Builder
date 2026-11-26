# News Post Builder

A local web application that extracts news articles, generates headline and description options using an LLM, allows selecting and editing, and creates a ready-to-publish WordPress post payload in dry-run mode.

---

## Architecture & Layers

The project follows a clean, layered architecture:

- `src/news_post_builder/core`: Pure business logic, domain models, ports/interfaces, and session state machine. Has no dependencies on web or adapters.
- `src/news_post_builder/adapters`: External system implementations (trafilatura extractor, SSRF-protected fetcher, LLM providers, WordPress client, SQLite repository).
- `src/news_post_builder/web`: FastAPI application, routes, Jinja2 templates, static assets.
- `prompts/`: Versioned LLM prompt templates (`generate_v1.md`).
- `data/`: Local storage for SQLite DB and dry-run JSON payloads (gitignored).

---

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

---

## Setup

1. **Create local virtual environment and install dependencies:**
   ```bash
   uv sync --all-extras
   ```

2. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to configure your LLM API key (e.g. `LLM_API_KEY`).

---

## Running the Application

To start the local development server:
```bash
uv run uvicorn news_post_builder.web.app:app --host 127.0.0.1 --port 8000 --reload
```
Check health:
```bash
curl http://127.0.0.1:8000/health
```

---

## CI & Quality Commands

- **Run all unit & integration tests:**
  ```bash
  uv run pytest
  ```
- **Lint & format checks (Ruff):**
  ```bash
  uv run ruff check .
  uv run ruff format --check .
  ```
- **Strict type checking (Mypy):**
  ```bash
  uv run mypy src tests
  ```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | App environment (`development`, `test`, `production`) |
| `APP_HOST` | `127.0.0.1` | Local bind address |
| `APP_PORT` | `8000` | Local port |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLite database URL |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LLM_PROVIDER` | `gemini` | LLM provider (`gemini`, `anthropic`, `mock`) |
| `LLM_MODEL` | `gemini-2.5-flash` | Model identifier |
| `LLM_API_KEY` | *(Required in non-test)* | API key for LLM provider |
| `LLM_TIMEOUT_SECONDS` | `60` | LLM request timeout |
| `LLM_MAX_RETRIES` | `3` | Max retry attempts for LLM errors |
| `HEADLINE_COUNT` | `3` | Number of headline suggestions per round |
| `DESCRIPTION_COUNT` | `3` | Number of description suggestions per round |
| `DESCRIPTION_MAX_CHARS`| `300` | Max character length for descriptions |
| `MAX_MORE_ROUNDS` | `5` | Maximum number of "more options" rounds |
| `PROMPT_VERSION` | `v1` | Prompt template version in `prompts/` |
| `FETCH_TIMEOUT_SECONDS`| `15` | Timeout for article HTTP fetching |
| `FETCH_MAX_BYTES` | `5000000` | Max response size for fetching (5MB) |
| `FETCH_USER_AGENT` | `NewsPostBuilder/1.0` | HTTP User-Agent string |
| `MIN_ARTICLE_CHARS` | `300` | Minimum extracted body length |
| `WP_BASE_URL` | `""` | WordPress site base URL |
| `WP_USERNAME` | `""` | WordPress username for Application Password |
| `WP_APP_PASSWORD` | `""` | WordPress Application Password |
| `WP_NEWS_CATEGORY_SLUG`| `news` | Category slug to resolve ID |
| `WP_NEWS_CATEGORY_ID` | `None` | Direct category ID override |
| `WP_POST_STATUS` | `draft` | Post status (`draft`, `publish`, etc.) |
| `WP_PUBLISH_ENABLED` | `false` | Gatekeeper for publishing (dry-run when false) |
| `WP_CONTENT_MAP` | `both` | Maps description to `both`, `content`, or `excerpt` |

---

## Dry-Run Publishing Behavior

When `WP_PUBLISH_ENABLED=false` (the default):
- No `POST`, `PUT`, `PATCH`, or `DELETE` requests are ever sent to WordPress.
- The app generates the complete WordPress REST payload (`title`, `content`, `excerpt`, `status`, `categories`).
- The payload is written to `./data/dry_run/<timestamp>.json` and displayed in the UI for review.
