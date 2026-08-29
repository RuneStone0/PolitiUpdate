# AGENTS.md

## What this is

PolitiUpdate mirrors Danish police press releases (Ritzau RSS feed) to X (@PolitiUpdate) within ~30s of publication. The repo is a set of small, independent Python apps under `src/`, each runnable as `python -m src.<app>`, sharing one SQLite database and one X API credential set. Python 3.12; dependencies in `requirements.txt`.

## Commands

Tests (unit + regression, ~154 tests; the 95% coverage gate is enforced via pyproject.toml `addopts`):

```bash
python -m pytest tests/ --ignore=tests/test_e2e.py
```

- Single test: `python -m pytest tests/test_formatter.py -k test_name --no-cov` (`--no-cov` skips the coverage gate when running a subset)
- E2E dry-run (fetches live RSS, never posts to X): `python tests/test_e2e.py`

Run services locally:

```bash
pip install -r requirements.txt
python -m src.bot.main      # main polling bot
python -m src.bot.auth      # one-time X authorization, saves refresh token to data/x_tokens.json
python -m src.notify        # persistent notify loop; also: `daily` | `weekly` one-shot modes
python -m src.digest        # weekly digest (needs LLM_API_KEY + GitHub tokens); --dry-run prints without publishing
python -m src.feedback      # monthly feedback tweet; --dry-run, --force, --month 2026-08
python -m src.x_stats       # X stats for website; --refresh forces a refetch
```

Docker:

```bash
docker compose up -d        # bot + notify (persistent services)
docker compose --profile manual run --rm weekly-post   # one-shot jobs: weekly-post, x-stats, feedback-post
docker compose -f docker-compose.test.yml run --rm test   # or: e2e
```

CI (GitHub Actions): `test.yml` runs unit + e2e + Docker tests; `publish.yml` builds/pushes `ghcr.io/runestone0/politiupdate` on test success; `release.yml` (release-please) versions from conventional commits on `main`; `deploy-pages.yml` deploys the static site. There is no configured linter — pytest with the coverage gate is the validation.

## Architecture

Five apps live under `src/`, each with its own env-driven `config.py` and CLI entrypoint:

- `src/bot` — the core polling loop: fetch RSS → dedupe → scrape press release page → format → post thread to X. Runs forever.
- `src/notify` — persistent self-scheduling service: daily bot health check + failed-post backlog, weekly X-stats/follower refresh, periodic "dropped stale" digest, and real-time ERROR-log forwarding to a Prowl webhook. No cron needed.
- `src/digest` — weekly digest: queries the bot DB for the past ISO week, categorizes posts by Danish keyword heuristics, generates a Danish narrative via DeepSeek, publishes to a GitHub Gist, commits static archive pages (`website/uge/{year}/{week}/`) via the GitHub Contents API, and posts a link tweet. Triggered by host cron (`--profile manual`).
- `src/feedback` — posts the monthly feedback-request tweet; its own scheduling gate (first Saturday of the month, DST-aware local time) decides whether a trigger is the right moment.
- `src/x_stats` — fetches X account metrics, caches to `website/x-stats.json`, publishes to a Gist. Also invoked by notify's weekly job.

### Bot data flow (the part that requires reading multiple files)

1. `fetcher.fetch_feed()` parses the Ritzau RSS feed. Each item's `guid` is a press-release URL with a `#sm-XXXXX` fragment targeting one specific update.
2. `db` (SQLite, WAL mode, `data/politiupdate.db`) dedupes by guid and by exact tweet text (`posted_texts` table) — catching re-published releases before X rejects them as duplicates.
3. `fetcher.fetch_press_release()` scrapes the release page for `div.thread-item` blocks. Multiple updates on one page post as an X thread: **newest first as the main tweet, older items as replies** (`poster.post_thread`).
4. `formatter.format_post()` builds `<district prefix>: <title>` + body, appends "Del gerne 🔁" for public-help posts, and condenses via DeepSeek (`summarizer.py`) when over `POST_MAX_CHARS` — with a safety-margin retry loop because DeepSeek reliably overshoots character budgets.
5. Post lifecycle in the DB: `fetching → posted | failed | skipped | dropped_stale`. `failed` posts are retried every ~80 polls; posts older than `MAX_ARTICLE_AGE_HOURS` are permanently given up on as `dropped_stale` — the one outcome notify actually alerts on (transient X 403/503s are intentionally logged as warnings, not errors).

### X auth (read before touching posting code)

Credentials come from env vars; OAuth 1.0a (free tier) is preferred, falling back to OAuth 2.0 PKCE bearer. Refresh tokens rotate on every use, so the persisted `data/x_tokens.json` file takes precedence over a static `X_REFRESH_TOKEN` env var — the env var only bootstraps a fresh/empty data volume. The `SCOPES` list in `poster.py`/`x_stats/main.py` must match what `auth.py` requested, or oauthlib raises on refresh.

### State files and double-fire protection

One-shot jobs (`digest`, `feedback`) and notify's loop persist "last ran" markers in `data/*_state.json` (shared volume) so a misfiring schedule or container restart never double-posts. If you add a scheduled job, mirror this pattern.

### Website

Static GitHub Pages site under `website/` (Danish; `uge/` = weekly digest archives). Digest archive pages and `x-stats.json` are committed by the apps themselves via the GitHub Contents API (PAT with `contents: write`; tokens `GITHUB_COMMIT_TOKEN` / `GITHUB_GIST_TOKEN`), not by a human. Pushing to `main` triggers the Pages deploy.

## Conventions and gotchas

- Never commit `.env*` variants or anything under `data/` (real tokens live there). `.env.example` documents every variable; `scripts/run-x-stats.sh` defaults to `.env.ProdPolitiUpdateBot` for local prod-adjacent runs.
- `tests/conftest.py` sets fake X credentials and forces `NOTIFY_ON_ERROR=0` so tests never touch the network or Prowl; `auth.py` is excluded from coverage.
- Config is read from env vars at import time; the `reset_config` fixture restores module-level config between tests. If you add a config knob, mirror that pattern.
- Keep the JSON-lines logging format used by `bot/main.py` (parsed by Docker's json-file driver).
- Docs: `docs/context.md` (purpose/strategy), `docs/PLAN.md` (deployment/roadmap), `README.md` (feature list and scheduling details).
