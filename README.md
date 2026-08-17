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
- **Monthly feedback request** — asks followers what they like and what to improve, once a month (`src/feedback`)
- **Notifications** — daily service health check and weekly follower-count summary, delivered via a Prowl webhook

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
4. Deploy — re-pull and redeploy the stack manually when a new image is pushed to `main`

### Docker Compose

```bash
# Copy .env.example and fill in credentials
cp .env.example .env
python -m src.bot.auth   # one-time authorization
docker compose up -d
```

The bot auto-refreshes the access token via `X_REFRESH_TOKEN` — no file mounts needed.

### Scheduling batch jobs

`x-stats`, `weekly-post`, and `feedback-post` are one-shot jobs (`restart: "no"`, `profiles: [manual]`) — they run once and exit, so something outside Compose needs to trigger them on a schedule (host cron, Portainer, etc.) if you want them to run automatically. The `manual` profile keeps them out of the default `docker compose up -d` set — without it, anything that re-runs `up -d` (e.g. Portainer's GitOps polling) restarts these exited containers on every poll; that caused a real incident where `x-stats` got re-triggered every 5 minutes for hours and hammered the GitHub Gist API into a 503 (see git history). Pass `--profile manual` explicitly to run them. Example host crontab:

```cron
# Weekly digest, Sundays 18:00 Danish time (CRON_TZ keeps it DST-safe)
CRON_TZ=Europe/Copenhagen
0 18 * * 0 cd /path/to/politiupdate && docker compose --profile manual run --rm weekly-post

# Monthly feedback request — trigger every Saturday at 17:00 UTC (18:00/19:00
# Danish time depending on DST); the app itself only posts on the first
# Saturday of the month, at/after 18:00 Danish time, and no-ops otherwise
# (see src/feedback's scheduling gate — cron can't express "first Saturday
# of the month" or a DST-aware local time directly, so the container is
# invoked more often than it actually posts). Reset CRON_TZ to UTC here —
# it persists to all following lines otherwise, which would shift this one.
CRON_TZ=UTC
0 17 * * 6 cd /path/to/politiupdate && docker compose --profile manual run --rm feedback-post
```

`notify` is **not** a batch job — it's a persistent service (`restart: unless-stopped`, like `bot`) that self-schedules its own daily health check and weekly X-stats refresh + follower notification internally (see [src/notify/loop.py](src/notify/loop.py)). No cron, Portainer scheduling, or GitHub Actions needed for it — `docker compose up -d` is enough. `x-stats`'s own periodic refresh is redundant with notify's weekly job (same X API call); the `x-stats` compose entry is kept only for on-demand manual refreshes.

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
| `PROWL_WEBHOOK_URL` | — | Webhook that receives `{"message": "..."}` POSTs for notifications (required; unauthenticated URL — keep it out of version control) |
| `BOT_HEALTH_URL` | `http://bot:8080/health` | Where `notify` checks bot health (compose service name) |
| `NOTIFY_FAILED_POSTS_THRESHOLD` | `3` | Alert when this many posts are stuck as `failed` |
| `NOTIFY_ON_ERROR` | `1` | Forward the bot's ERROR-level logs to Prowl in real time (`0` to disable) |
| `NOTIFY_DAILY_HOUR_UTC` | `9` | Hour (UTC) the persistent `notify` service runs its daily health check |
| `NOTIFY_WEEKLY_WEEKDAY` / `NOTIFY_WEEKLY_HOUR_UTC` | `6` (Sunday) / `10` | When `notify` runs its weekly stats + follower check |

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
src/feedback/     Monthly feedback-request tweet (standalone, run monthly)
src/notify/
  prowl.py        Prowl webhook client
  health.py       Daily check: bot /health + failed-post backlog
  weekly.py       Weekly check: X-stats refresh + follower-count delta
  loop.py         Persistent self-scheduling loop (like bot/main.py)
  main.py         CLI entrypoint (no args = loop; `daily` | `weekly` = one-shot)
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
