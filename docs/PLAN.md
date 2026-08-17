# PolitiUpdate — Plan & Roadmap

## Objective
Ship a bot that mirrors Danish police short messages to @PolitiUpdate faster and more completely than @PolitiUpdate0, grow the audience, and (optionally) monetize. Full financial analysis in financials.md.

## Project structure
```
src/bot/           Application code
  config.py          Environment-driven settings (X_PRO, LLM toggles)
  db.py              SQLite deduplication and post tracking (WAL mode)
  fetcher.py         RSS polling + press release scraping (thread-item parser)
  formatter.py       Post formatting (district prefix, truncation, LLM condense)
  poster.py          X API v2 posting via tweepy (rate-limit handling, threading)
  summarizer.py      DeepSeek API summarization (OpenAI-compatible)
  health.py          Background HTTP /health endpoint for Docker health checks
  main.py            Polling loop (fetch → dedupe → format → post → retry)
docs/               Documentation (context.md, PLAN.md, financials.md)
tests/              Unit + regression + e2e tests (146 tests, 99% coverage)
```

## Build constraints (driving decisions)
- **Link-free posts** — avoids the $0.20/post URL surcharge.
- **Full-message posts** — requires X Premium's long-post feature (>280 chars).
- **30–60s polling** — cannot use GitHub Actions (5-minute cron minimum) → run locally on UmbrelOS (Portainer/Docker).
- **Dedupe by RSS `<guid>`** — no reposts.
- **Danish as-is** — X auto-translates on the viewer side; no translation work.

## Phase 1 — MVP bot ✅

**Implemented:**

- 30s RSS polling with live feed
- Multi-update thread support — pages with multiple timestamped entries post as X threads (latest = main tweet, older = replies)
- Press release scraper with `thread-item` div parsing, district extraction, `&nbsp;` normalization
- SQLite deduplication by RSS `<guid>` (WAL mode, busy timeout)
- X API v2 posting via tweepy (OAuth 1.0a) with rate-limit backoff and retry
- Three-tier post formatting:
  - **X_PRO=1**: full-length posts up to 25,000 chars (Premium)
  - **LLM_ENABLED=1**: DeepSeek condenses posts exceeding `POST_MAX_CHARS`, preserving key facts, retrying with a tighter target if the first attempt still overshoots
  - **Default**: clean sentence-boundary truncation at 280 chars with `…`
- **Retweet prompt** — auto-appends `Del gerne 🔁` to public-help posts (efterlysning, savnet, kontakt politiet, har du set, etc.). Space is reserved before truncation so prompt never pushes post past 280 chars.
- Failed post retry — sweeps failed posts every ~1 hour and re-attempts
- Structured JSON logging
- Docker packaging (Dockerfile + compose) for UmbrelOS/Portainer
- Docker `/health` endpoint (checks DB, RSS reachability, uptime, last poll)
- GitHub Actions CI (pip unit tests + Docker test build/e2e)
- 146 tests at 99% coverage, regression tests against known press releases
- `--cov-fail-under=95` enforcement

**Pending:** X API credentials for live run.

## Phase 2 — Run on UmbrelOS (Portainer) ✅
- Docker Compose stack: app service + SQLite volume
- Secrets via env file (`.env` with X API keys), restart policy
- HEALTHCHECK via `/health` endpoint (60s interval, 3 retries)
- Log rotation: 10MB × 3 files (json-file driver)
- Monitor logs; keep latency low

## Phase 3 — Weekly AI summaries
- Generate weekly digest of the week's items with an LLM
- Post as original content, disclosed as AI-generated, format varied weekly

## Phase 4 — Website ✅
- Landing page explaining what PolitiUpdate is and how to use it
- Live X stats (post count, followers) pulled from GitHub Gist
- District filtering instructions using X search (`from:PolitiUpdate Nordjylland`, etc.)
- Notification setup guide for followers
- Responsive dark-themed design, favicon
 - Add the website URL to the X profile once the site is live.

## Phase 4.5 — Follower automation ❌ Retired
- `src/followers` — standalone app: followed back new followers, unfollowed anyone who unfollowed
- Retired 2026-08-17: X removed Following (and Follows-relationship API writes generally) from
  all self-serve tiers on 2026-04-20, moving it to Enterprise-only access. No token/config fix
  restores this — the account's paid "Pay Per Use" plan can no longer be granted `follows.read`/
  `follows.write` at all, so the feature is permanently non-functional on this plan. Code removed.

## Phase 5 — Multi-channel replication (future)
- Mirror posts to Instagram, Facebook, etc.

## Phase 5.5 — Monthly feedback request ✅
- `src/feedback` — standalone app: posts a monthly tweet asking followers what they like and what to improve
- Local state tracking (`FEEDBACK_STATE_PATH`) so a misfiring schedule doesn't double-post
- `feedback-post` compose service, scheduled like `weekly-post` (host cron/Portainer)

## Future improvements / backlog
- **Feedback polls / website feedback** — the X-post half of "request feedback via X posts/polls, website" is done (Phase 5.5); polls and a website feedback channel are still open. Understand what followers value most (speed, completeness, district filtering, English summaries).
- **Reply-listening bot** — monitor @PolitiUpdate's X mentions/replies, auto-collect feature requests and sentiment, triaged by LLM.
- Multi-channel (Phase 5)
- English summaries for international audience (biggest revenue lever per financials.md)
- Analytics: track which posts drive profile visits/follows
- Own funnel: drive followers to a site/newsletter we control

## Prerequisites / open items
- X API Project/App + OAuth 1.0a keys with write access
- X Premium subscription (needed for long posts; later monetization)
