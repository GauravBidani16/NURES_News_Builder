# News Post Builder

A local web application that converts news articles into ready-to-publish WordPress posts with AI-generated suggestions, automated image selection, and safe dry-run publishing.

---

## Architecture & Layers

The project strictly follows a clean, hexagonal architecture:

```
src/news_post_builder/
  core/           # Domain models, state machine, service layer, and ports (zero framework/external imports)
  adapters/       # External integrations:
                  #   - fetcher: SSRF-protected streaming HTTP client
                  #   - extractor: Trafilatura HTML & text extractor
                  #   - llm: Google Gemini provider with model redundancy & prompt manager
                  #   - publishers: DryRunPublisher & WordPressPublisher
                  #   - repository: SQLite WAL-mode session store (./data/app.db)
                  #   - payload_builder: Verified WordPress post layout builder
  web/            # FastAPI application, dependency injection, routes, and Jinja2 templates
prompts/          # Versioned prompt templates (generate_v1.md)
data/             # Local database and dry-run JSON payloads (gitignored)
tests/            # 100% offline unit and integration test suite
```

### State Machine Lifecycle

```
NEW --submit(url|text)--> FETCHING
FETCHING --ok--> OPTIONS_READY
FETCHING --fail--> FETCH_FAILED   (shows specific reason; offers direct paste fallback)
OPTIONS_READY --more(headlines|descriptions|both)--> OPTIONS_READY   (options accumulate)
OPTIONS_READY --select(headline_id, description_id)--> PREVIEW
PREVIEW --back--> OPTIONS_READY
PREVIEW --confirm--> DONE   (dry-run: payload saved locally; zero WordPress requests)
```

---

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

---

## Quickstart

1. **Install dependencies and create virtualenv:**
   ```bash
   uv sync --all-extras --python 3.12
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   ```
   Ensure your `.env` contains your Gemini API key:
   ```dotenv
   LLM_API_KEY=your_gemini_api_key_here
   ```

3. **Start the local web application:**
   ```bash
   uv run uvicorn news_post_builder.web.app:app --host 127.0.0.1 --port 8000 --reload
   ```
   Open your browser to: [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `development` | Application environment (`development`, `test`, `production`) |
| `APP_HOST` | `127.0.0.1` | Local bind address |
| `APP_PORT` | `8000` | Local port |
| `DATABASE_URL` | `sqlite:///./data/app.db` | Local SQLite database file location |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LLM_PROVIDER` | `gemini` | LLM provider (`gemini`, `mock`) |
| `LLM_MODEL` | `gemini-3.5-flash-lite` | Primary AI model |
| `LLM_FALLBACK_MODELS` | `gemini-2.5-flash,gemini-2.5-flash-lite` | Automatic fallback models if primary model fails |
| `LLM_API_KEY` | *(Required)* | Google Gemini API Key |
| `LLM_TIMEOUT_SECONDS` | `60` | Request timeout for AI generation |
| `LLM_MAX_RETRIES` | `3` | Max retry attempts with exponential backoff on 429/5xx |
| `HEADLINE_COUNT` | `3` | Number of headline options generated per round |
| `DESCRIPTION_COUNT` | `3` | Number of description options generated per round |
| `DESCRIPTION_MAX_CHARS`| `300` | Maximum character length for descriptions |
| `MAX_MORE_ROUNDS` | `5` | Maximum rounds of "+ More Options" permitted |
| `PROMPT_VERSION` | `v1` | Active prompt template in `prompts/` |
| `FETCH_TIMEOUT_SECONDS`| `15` | Timeout for article HTTP fetching |
| `FETCH_MAX_BYTES` | `5000000` | Maximum download size for article pages (5MB) |
| `FETCH_USER_AGENT` | `NewsPostBuilder/1.0` | Custom User-Agent header for fetching |
| `MIN_ARTICLE_CHARS` | `300` | Minimum readable characters required from article |
| `WP_BASE_URL` | `https://nudvnures.wpenginepowered.com` | Target WordPress site URL |
| `WP_USERNAME` | `""` | WordPress username (for live publishing if enabled) |
| `WP_APP_PASSWORD` | `""` | WordPress Application Password |
| `WP_NEWS_CATEGORY_SLUG`| `news` | Category slug for News |
| `WP_NEWS_CATEGORY_ID` | `31` | Verified WordPress News Category ID |
| `WP_POST_STATUS` | `draft` | Post status (`draft`, `publish`, `pending`) |
| `WP_PUBLISH_ENABLED` | `false` | **Safety gatekeeper** (stays `false` for dry-run mode) |
| `WP_FEATURED_MEDIA_NIH_ID` | `4732` | WordPress Media ID for NIH Logo (`nih_logo.png`) |
| `WP_FEATURED_MEDIA_DEFAULT_ID` | `4749` | WordPress Media ID for default featured image |

---

## Safe Dry-Run Publishing Behavior

When `WP_PUBLISH_ENABLED=false` (the default):
1. **Zero HTTP requests** are sent to your WordPress site.
2. The app formats the complete WordPress REST payload (`title`, `excerpt`, `content`, `status`, `categories: [31]`, `featured_media: 4732|4749`).
3. The exact payload is saved locally to `./data/dry_run/<timestamp>_<session_id>.json`.
4. The web UI displays the saved payload file path and syntax-highlighted JSON.

---

## Quality & Test Commands

- **Run all tests (100% offline/mocked):**
  ```bash
  uv run pytest
  ```
- **Lint code (Ruff):**
  ```bash
  uv run ruff check .
  ```
- **Format code check (Ruff):**
  ```bash
  uv run ruff format --check .
  ```
- **Strict type checking (Mypy):**
  ```bash
  uv run mypy src tests
  ```

---

## Manual Walkthrough Checklist

Follow this checklist to test the application in your browser:

- [ ] **1. Start App**: Run `uv run uvicorn news_post_builder.web.app:app --reload` and visit `http://127.0.0.1:8000`.
- [ ] **2. Submit URL**: Paste `https://grants.nih.gov/grants/guide/notice-files/NOT-OD-26-131.html` and click **Fetch & Generate Options**.
- [ ] **3. Review Suggestions**:
  - Verify 3 headlines and 3 descriptions appear.
  - Notice the **★ Top Recommendation** badge on the top choice.
- [ ] **4. Test "More Options"**: Click **+ More Headlines** or **+ More Both**.
  - Verify new suggestions are added to the list without erasing the original options.
- [ ] **5. Test Manual Editing**:
  - Select an option via radio button.
  - Tweak the text inside the editable text box below it.
- [ ] **6. Preview Post**: Click **Review Post Preview**.
  - Verify the **Featured Image** displays the NIH logo (Media ID: `4732`).
  - Verify the Category is **News** (`[31]`).
  - Verify the post layout matches your site: 2-sentence description followed by the `"Get more details here:"` source link.
- [ ] **7. Confirm Post**: Click **Confirm Post**.
  - Verify the green success banner appears.
  - Verify the exact JSON payload is displayed.
  - Check `./data/dry_run/` in your terminal to see the saved `.json` file!
- [ ] **8. Test Failure Fallback**:
  - Click **Start Another News Post**.
  - Enter a bad URL (e.g. `https://example.com/not-found-404`).
  - Verify the friendly failure banner appears explaining the issue, with the direct paste-text fallback box ready for use.
