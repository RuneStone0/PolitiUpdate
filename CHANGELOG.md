# Changelog

## [1.1.0](https://github.com/RuneStone0/PolitiUpdate/compare/v1.0.0...v1.1.0) (2026-08-04)


### Features

* auto-update PR branches when main changes ([570a6a7](https://github.com/RuneStone0/PolitiUpdate/commit/570a6a71419532e76ff2d0e6cbd6b46cf63cddb8))
* automate releases with release-please ([b35305f](https://github.com/RuneStone0/PolitiUpdate/commit/b35305f2e0684163842106b9216b4d768e99e10a))


### Bug Fixes

* auto-update PRs targeting any base branch ([00d833f](https://github.com/RuneStone0/PolitiUpdate/commit/00d833fbdf56751d0099f1e6fc28119924285453))

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
