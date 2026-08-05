# PolitiUpdate

> Fast, complete mirror of Danish police updates on X.

[@PolitiUpdate](https://x.com/PolitiUpdate) pulls short messages from the official Danish police RSS feed and posts them to X within ~30 seconds of publication — beating the competition on speed and completeness. Link-free, all 14 districts, threaded updates, and optional AI summaries. Unofficial and citizen-run; not affiliated with the police.

## Features

- **Fast** — posts within ~30s of publication (competitor averages ~60s)
- **Complete** — covers all 14 Danish police districts with full message text (X Premium for >280 chars)
- **Threaded updates** — multi-entry press releases post as X threads (newest first, older as replies)
- **Smart summaries** — optional LLM condensation of long posts via DeepSeek, preserving key facts
- **Del gerne 🔁** — auto-appends a retweet prompt on public appeals (missing persons, witness calls)
- **Link-free** — avoids X's per-URL surcharge (~$7/mo saved)
- **Failed post retry** — sweeps undelivered posts every ~1 hour
- **Health check** — built-in HTTP `/health` endpoint for container monitoring

## Quick start

### 1. Clone and set up credentials

```bash
cp .env.example .env
```

Fill in `X_CLIENT_ID` and `X_CLIENT_SECRET` from the [X Developer Portal](https://developer.x.com/en/portal) (your App → Keys and tokens → OAuth 2.0 section).

### 2. Authorize the bot (one-time)

```bash
python -m src.bot.auth
```

Opens a browser for X authorization. Saves a refresh token to `data/x_tokens.json`. For Docker deployment, copy the printed `X_REFRESH_TOKEN` value.

### 3. Run locally

```bash
docker compose up -d
docker compose logs -f
```

Or without Docker:

```bash
pip install -r requirements.txt
python -m src.bot.main
```

## Deployment

See the full deployment guide in [docs/PLAN.md](docs/PLAN.md#phase-2--run-on-umbrelos-portainer).

### Portainer (UmbrelOS)

1. Make the [GHCR package public](https://github.com/RuneStone0/PolitiUpdate/pkgs/container/politiupdate) (one-time)
2. **Stacks** → **Add stack**, paste `docker-compose.yml`
3. Add environment variables:
   ```
   X_CLIENT_ID=...
   X_CLIENT_SECRET=...
   X_REFRESH_TOKEN=...   # from python -m src.bot.auth
   ```
4. Deploy — Watchtower auto-updates on new `main` pushes

### Docker Compose

```bash
# Copy .env.example and fill in credentials
cp .env.example .env
python -m src.bot.auth   # one-time authorization
docker compose up -d
```

The bot auto-refreshes the access token via `X_REFRESH_TOKEN` — no file mounts needed.

## Testing

```bash
# Unit + regression tests (154 tests, 100% coverage)
python -m pytest tests/ --ignore=tests/test_e2e.py

# End-to-end dry-run (fetches live RSS)
python tests/test_e2e.py

# Docker test suite
docker compose -f docker-compose.test.yml build
docker compose -f docker-compose.test.yml run --rm test
docker compose -f docker-compose.test.yml run --rm e2e
```

## Configuration

| Env var | Default | Description |
|---|---|---|
| `X_CLIENT_ID` | — | OAuth 2.0 client ID (required) |
| `X_CLIENT_SECRET` | — | OAuth 2.0 client secret (required) |
| `X_REFRESH_TOKEN` | — | Refresh token for headless/Docker auth |
| `X_PRO` | `0` | Enable full-length posts (needs X Premium) |
| `LLM_ENABLED` | `0` | Enable LLM condensation (needs `LLM_API_KEY`) |
| `POLL_INTERVAL_SECONDS` | `30` | RSS polling interval |
| `POST_MAX_CHARS` | `280` | Max post length (`25000` with `X_PRO`) |
| `HEALTH_PORT` | `8080` | Health check HTTP port (`0` to disable) |
| `LOG_LEVEL` | `INFO` | Logging level |

See [`.env.example`](.env.example) for all options.

## Project structure

```
src/bot/
  config.py       Environment-driven settings
  db.py           SQLite deduplication (WAL mode)
  fetcher.py      RSS polling + press release scraper
  formatter.py    Post formatting, truncation, LLM condense
  poster.py       X API v2 posting (OAuth 2.0, auto-refresh)
  summarizer.py   DeepSeek API summarization
  health.py       HTTP /health endpoint
  main.py         Polling loop (fetch → dedupe → format → post)
  auth.py         One-time OAuth 2.0 PKCE authorization
docs/             Project context, roadmap, financials
tests/            154 tests at 100% coverage
```

## Docs

- [context.md](docs/context.md) — purpose, source, competition, strategy
- [PLAN.md](docs/PLAN.md) — build phases, deployment, roadmap
- [financials.md](docs/financials.md) — costs, revenue model, monetization odds

## Source

- RSS feed: https://via.ritzau.dk/rss/short-messages/latest (all districts, Danish)
- Official page: https://politi.dk/en/current-affairs/get-politi-update-as-an-rss-feed
