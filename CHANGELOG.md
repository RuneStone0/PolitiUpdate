# Changelog

## [1.3.0](https://github.com/RuneStone0/PolitiUpdate/compare/v1.2.0...v1.3.0) (2026-08-06)


### Features

* add website URL to X profile for future updates ([6c8696e](https://github.com/RuneStone0/PolitiUpdate/commit/6c8696ea9885bf230ff91947f966a4842e885988))
* support both OAuth 1.0a (free tier) and OAuth 2.0 (basic tier+) ([5d037b9](https://github.com/RuneStone0/PolitiUpdate/commit/5d037b90a70b6aa93418615d3c82be7e38b2dc5d))
* **website:** add PolitiUpdate landing page with live X stats ([18955eb](https://github.com/RuneStone0/PolitiUpdate/commit/18955ebd65028a5b246b938d68da8feb774a4407))


### Bug Fixes

* update .gitignore to ignore all env variants except the example ([19a667d](https://github.com/RuneStone0/PolitiUpdate/commit/19a667d47520146a35c4c94b5e1989f36af7aab6))
* update publish workflow to trigger on successful completion of Test workflow ([7f21373](https://github.com/RuneStone0/PolitiUpdate/commit/7f21373f42a672aa2c4673870a253456347ff0a7))

## [1.2.0](https://github.com/RuneStone0/PolitiUpdate/compare/v1.1.1...v1.2.0) (2026-08-04)


### Features

* switch to OAuth 2.0 PKCE for X API posting ([2e40798](https://github.com/RuneStone0/PolitiUpdate/commit/2e407989b0ebd1e62dd75fdd0e4cf5c4cfe305f4))
* switch to OAuth 2.0 PKCE for X API posting ([a7f20b5](https://github.com/RuneStone0/PolitiUpdate/commit/a7f20b5e3f8763e172b7059cb7820e615e418435))

## [1.1.1](https://github.com/RuneStone0/PolitiUpdate/compare/v1.1.0...v1.1.1) (2026-08-04)


### Bug Fixes

* pass env vars from Portainer stack.env and add heartbeat logs ([0f94057](https://github.com/RuneStone0/PolitiUpdate/commit/0f940577facddf124726dc161d4e62a874daceaa))
* pass env vars from Portainer stack.env and add startup/heartbeat logs ([5308c9c](https://github.com/RuneStone0/PolitiUpdate/commit/5308c9c9892fda93f7732e2bb573c029ceb9bd4f))

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
