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

1. Create a new stack in Portainer, paste the contents of `docker-compose.yml`
2. Add the following environment variables to the stack (or upload your `.env`):
   ```
   X_API_KEY=...
   X_API_SECRET=...
   X_ACCESS_TOKEN=...
   X_ACCESS_SECRET=...
   ```
3. Deploy the stack

The image is automatically built and pushed to `ghcr.io/runestone0/politiupdate` on every push to `main`. Watchtower checks every 60 seconds and redeploys when a new image is available — no manual deploys needed.

### Local

```bash
cp .env.example .env
# Edit .env with your X API keys

docker compose -f docker-compose.test.yml build
docker compose -f docker-compose.test.yml run --rm test
docker compose -f docker-compose.test.yml run --rm e2e

docker compose up -d
docker compose logs -f
```
