# Financial Headlines Digest (Isolated)

Bilingual (EN/CN) financial headlines digest with summaries and links. Sends twice daily at 08:00 America/New_York and 08:00 Asia/Shanghai.

## Setup

1. Activate the venv:
   `source .venv/bin/activate`
2. Install dependencies:
   `pip install -r fin_news_digest/requirements.txt`
3. Copy and edit env:
   `cp fin_news_digest/.env.example .env`
4. Update `SMTP_*` and `RECIPIENTS` in `.env`.
5. Optional: adjust `fin_news_digest/sources.json`.

## Run Once (manual test)

`python fin_news_digest/run_once.py --edition "Manual"`

## Run Scheduler (twice daily)

`python fin_news_digest/scheduler.py`

## Translation

Set `TRANSLATE_PROVIDER` to:
- `mymemory` (default, free, rate-limited)
- `libretranslate` (use `TRANSLATE_ENDPOINT` and optional `TRANSLATE_API_KEY`)
- `none` (no translation)

## Optional: LLM Re-Rank (OpenAI)

Enable LLM-based ranking for better news taste:

- `OPENAI_API_KEY` (required)
- `OPENAI_MODEL` (default: `gpt-5-mini`)
- `OPENAI_RERANK=true`
- `OPENAI_CANDIDATES=50` (cost control)

The pipeline will first do heuristic ranking, then call the model to re-rank the top candidates.

## Market Snapshot (Prev Close)

Enable a daily market snapshot section with major US / Europe indices (Alpha Vantage),
China indices (Eastmoney, no key), crypto, gold & silver.

- `ALPHA_VANTAGE_API_KEY` (required for market data)
- `ALPHA_VANTAGE_SLEEP_SECONDS=12` (rate-limit friendly)
- `MARKET_SNAPSHOT=true`

## Daily Chinese Outlook

Enable a short Chinese summary paragraph at the top:

- `OPENAI_SUMMARY=true`
- Requires `OPENAI_API_KEY`

## Notes

- Only headlines + short summaries + links are sent. No full-text content.
- `fin_news_digest/state.json` is used to avoid resending items across runs.
- Beijing 08:00 edition boosts China-related keywords; New York 08:00 boosts U.S./global keywords.
- If fewer than `MIN_ITEMS` are available, the pipeline expands the lookback to `FALLBACK_LOOKBACK_HOURS`.

## GitHub Actions (No Local Machine Required)

This workflow runs twice daily without your computer:
- 08:00 America/New_York (handles DST)
- 08:00 Asia/Shanghai

### Setup Steps

1. Push this repo to GitHub.
2. Add GitHub Secrets (Repo Settings -> Secrets and variables -> Actions):
   - `FIN_RECIPIENTS`
   - `FIN_SMTP_HOST`
   - `FIN_SMTP_PORT`
   - `FIN_SMTP_USER`
   - `FIN_SMTP_PASS`
   - `FIN_SMTP_FROM`
   - `FIN_SMTP_USE_TLS`
   - Optional: `FIN_TRANSLATE_PROVIDER`, `FIN_TRANSLATE_ENDPOINT`, `FIN_TRANSLATE_API_KEY`
3. The workflow file is at `.github/workflows/fin_news_digest.yml`.

Notes:
- GitHub Actions runners are stateless. If you want cross-run dedupe persistence, we can add an external state store (S3, Redis) or commit state updates to a private branch.
