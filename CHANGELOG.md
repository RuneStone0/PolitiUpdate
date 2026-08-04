# Changelog

## [1.0.0] — 2026-08-04

### Added
- 30s RSS polling from Via Ritzau (all 14 Danish police districts)
- Multi-update thread support (pages with multiple timestamps post as X threads)
- Three-tier post formatting: truncation (280 chars), LLM summarization (DeepSeek), full-length (X Premium)
- Retweet prompt auto-appended to public-help posts (efterlysning, savnet, etc.)
- SQLite deduplication by RSS `<guid>`
- Failed post retry (~every hour)
- Docker `/health` endpoint (DB, RSS reachability, uptime checks)
- GitHub Actions CI (unit, e2e, Docker jobs)
- Watchtower auto-deploy via Portainer
- GHCR image publishing with semver tags
- 146 tests at 99% coverage with regression tests

[1.0.0]: https://github.com/RuneStone0/PolitiUpdate/releases/tag/v1.0.0
