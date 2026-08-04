# PolitiUpdate

Automated Danish police updates (Politi Update) mirrored to X ([@PolitiUpdate](https://x.com/PolitiUpdate)). Pulls short messages from the official Danish police RSS feed (Via Ritzau) and posts them link-free within ~30 seconds of publication. Unofficial — not affiliated with the police.

**Status:** Phase 1 implemented. Ready for deployment to UmbrelOS.

## Features
- **Fast** — posts within ~30s of police publication, beating the competition
- **Complete** — all 14 Danish police districts, full message text (with X Premium)
- **Threaded updates** — when a press release gets updated, all timestamped entries post as a single X thread
- **Smart summaries** — optionally condenses long posts with an LLM while keeping every fact intact
- **"Del gerne 🔁"** — auto-appends a retweet prompt when the police ask the public for help (missing persons, witness appeals)
- **No links** — avoids X's per-post URL surcharge, saving ~$7/mo

## Quick facts
- Source: https://via.ritzau.dk/rss/short-messages/latest (all districts, Danish)
- Official page: https://politi.dk/en/current-affairs/get-politi-update-as-an-rss-feed

## Docs
- [context.md](docs/context.md) — purpose, source, competition, strategy, growth playbook
- [PLAN.md](docs/PLAN.md) — build phases, deployment, roadmap, backlog
- [financials.md](docs/financials.md) — costs, revenue model, odds

## Testing

```bash
# Unit + regression tests (146 tests)
python -m pytest tests/ --ignore=tests/test_e2e.py

# End-to-end dry-run (fetches live RSS, tests all three modes)
DRY_RUN=1 python tests/test_e2e.py

# E2E with X Premium mode
DRY_RUN=1 X_PRO=1 python tests/test_e2e.py

# Docker
docker compose -f docker-compose.test.yml build
docker compose -f docker-compose.test.yml run --rm test
docker compose -f docker-compose.test.yml run --rm e2e
```

## Deployment

### UmbrelOS / Portainer

**One-time setup:** make the GHCR package public so Portainer can pull it without authentication:

1. Go to https://github.com/RuneStone0/PolitiUpdate/pkgs/container/politiupdate
2. Package settings → Change visibility → **Public**

Then in Portainer:

**Step A — Run auth locally** (on your laptop, not in Portainer):

```bash
cp .env.example .env
# Fill in X_CLIENT_ID and X_CLIENT_SECRET from the X Developer Portal
python -m src.bot.auth
```

This will print your `X_REFRESH_TOKEN`. Copy it.

**Step B — Deploy in Portainer:**

1. **Stacks** → **Add stack**
2. Name: `politiupdate`
3. Paste the contents of `docker-compose.yml`
4. Under **Environment variables**, add:
   ```
   X_CLIENT_ID=...
   X_CLIENT_SECRET=...
   X_REFRESH_TOKEN=...   ← from Step A
   ```
5. Deploy

The bot auto-refreshes the access token using `X_REFRESH_TOKEN` — no file mounts needed.

**How it works:**
- Push to `main` → CI builds and pushes to `ghcr.io/runestone0/politiupdate:latest`
- Watchtower checks every 60s → pulls new image → redeploys
- No manual deploys needed

**Creating a release:**
1. Bump the version in `CHANGELOG.md`
2. Create a [GitHub Release](https://github.com/RuneStone0/PolitiUpdate/releases/new) with a semver tag (`v1.0.0`)
3. The publish workflow tags the image as `v1.0.0`, `v1.0`, and `v1`

### Local

```bash
cp .env.example .env
# Edit .env with your X OAuth 2.0 credentials (X_CLIENT_ID, X_CLIENT_SECRET)

# One-time: authorize and get a refresh token (saves to data/x_tokens.json)
python -m src.bot.auth

docker compose -f docker-compose.test.yml build
docker compose -f docker-compose.test.yml run --rm test
docker compose -f docker-compose.test.yml run --rm e2e

docker compose up -d
docker compose logs -f
```
