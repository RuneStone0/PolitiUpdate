# PolitiUpdate — Project Context

## Purpose
Build a service that pulls short messages from the Danish police RSS feed (Politi Update) and automatically posts them to the X account **@PolitiUpdate**. The Danish police have stopped posting updates directly to X; we mirror their official source. Unofficial, citizen-driven — not affiliated with the police.

## Official source
- Page: https://politi.dk/en/current-affairs/get-politi-update-as-an-rss-feed
- Feed (all districts, Danish): https://via.ritzau.dk/rss/short-messages/latest
- Format: RSS 2.0 (Via Ritzau). Item fields: `<title>`, `<link>` (press release permalink), `<description>` (usually empty), `<pubDate>` (GMT), `<guid>` (unique — use for dedupe), `<regulatory>` (bool)
- Per-district feeds via `?publisherId=<id>`:
  - Bornholm: 90799
  - Funen: 90797
  - Copenhagen: 90685
  - Western Copenhagen: 90718
  - Central and West Jutland: 90687
  - Central and West Zealand: 13562881
  - National Special Crime Unit: 13562884
  - North Jutland: 13562880
  - North Zealand: 90719
  - South Jutland: 90686
  - South East Jutland: 90720
  - South Zealand and Lolland-Falster: 90594
  - East Jutland: 90721
  - Danish National Police: 90752

## Competition: PolitiUpdate0
- @PolitiUpdate0, joined 2026-01-15, ~1,950 followers, ~3,000 posts (~15/day), Premium-verified
- Behavior: posts title + message with district prefix (e.g. "Sydsjælland/L-F |"), update messages prefixed 🔄️
- Speed measurement (2026-08-03): posts ~23–93s after RSS pubDate (avg ~60s) → their poll interval ≈ 60–90s
- Implication: we can beat them with 30–60s polling (expected ~15–45s latency)

## Strategy decisions
- **Post in Danish as-is** — no translation. X auto-translates on the viewer side; translation is NOT a differentiator.
- **Link-free posts** — avoids $0.20/post URL surcharge (see financials.md). Police link goes in bio or pinned post.
- **Full-message posts** — requires X Premium's long-post feature (>280 chars). Paid account is needed for the product, not just monetization.
- **Weekly AI-written summaries** (disclosed as AI-generated) — the "original content" play against aggregator cuts; drives shareable/verified engagement. Vary the format weekly (templated digests risk monetization-ineligible "repetitive content").
- **High-frequency polling** (30–60s) to beat PolitiUpdate0 on speed.
- **Run locally on UmbrelOS (Portainer/Docker)** — GitHub Actions cron has a 5-minute minimum, so it can't do 30–60s polling; local also avoids GHA spend.
- **Future: simple website** listing updates filterable by district, plus consistent district tags in posts so people can filter on X.
- **Future: multi-channel replication** (Instagram, Facebook, etc.).

## Growth playbook vs PolitiUpdate0
- Beat them on speed and completeness (full message, all districts) — followers of emergency feeds follow for speed.
- Serve the unmet need in public: reply to their snippet posts with the full text when useful (manual, sparingly).
- Win search/discovery: Danish keywords (district names, efterlysning, savnet, grundlovsforhør), consistent post format, clean bio + pinned explainer, link to official source.
- Position as reliable unofficial mirror of politi.dk (no impersonation; trust is the moat).
- Cross-pollinate where police actually publish (politi.dk, Facebook, local news).
- Guardrails: no bought followers/bots, no follow/unfollow churn, no DM spam, no impersonation — shadowban/monetization rejection risks kill the plan.

## Status log
- 2026-08-03: Project started. Feed structure inspected. Monetization analysis done.
- 2026-08-04: Repo initialized (remote README pulled). Docs reorganized into README.md / context.md / PLAN.md / financials.md. PolitiUpdate0 speed measured (~60s avg latency; beatable). Phase 1 MVP implemented: bot package with RSS polling, press release scraper (via.ritzau.dk), SQLite dedupe, X API posting via tweepy, Docker packaging. All modules tested — pending X API credentials for live run.
