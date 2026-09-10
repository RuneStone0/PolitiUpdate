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

## Phase 3 — Weekly AI summaries ✅
- `src/digest` — generates a weekly Danish narrative of the week's items via DeepSeek (neutral, journalistic tone), with notable-case picks linked back to real posts
- Categorizes posts by Danish keyword heuristics (efterlysninger, vidneappeller, anholdelser/sigtelser, øvrige)
- Publishes to a GitHub Gist, commits static archive pages (`website/uge/{year}/{week}/`), and posts a link tweet (varied headline templates)
- Scheduled Sunday 18:00 Danish (DST-aware) via a Hermes cron job → `python -m src.digest`; weeks 33–35 posted live
- ⚠️ Open gap: the original "disclosed as AI-generated" bullet — the narrative and tweet carry no AI disclosure label today

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
- **Newsletter + owned funnel (free, region-specific)** — a free weekly briefing email is the owned-audience engine; monetization is external to subscribers (sponsor/geo-targeted placements + B2B data later, per Rune 2026-09), never a consumer paywall. Subscriber picks a region; national releases auto-included everywhere. The region filter pulls straight from the existing `posts.district` column — no new ingestion, no schema change. Region grouping:
  - Copenhagen/Hovedstaden: København, Københavns Vestegn, Nordsjælland, Bornholm
  - Sjælland (rest): Midt/Vestsjælland, Sydsjælland/L-F
  - Jutland: Nordjylland, Midt/Vestjylland, Østjylland, Sydøstjylland, Sydjylland
  - Fyn: Fyn
  - National: Rigspolitiet, NSK, Politiskolen
  - *Progress (2026-09-09):* region-map (`src/common/regions.py`) + the `python -m src.newsletter --dry-run` pipeline (DB → region group → per-region briefing, national auto-included) are built & tested. The Brevo signup form is **live** on the site (sibforms embed), and `src/newsletter/sender.py` is implemented — transactional email via `POST /v3/smtp/email` (one call per recipient, GDPR-safe) plus region-contact fetch via `GET /v3/contacts` (9 sender tests). Still gated on: `BREVO_API_KEY` + authenticated sending domain (deferred to +10 signups), and a `region` field on the signup form (the form currently captures email only).
  - *Progress (2026-09-10):* Brevo `REGION` contact attribute **created via API**; first real signup **verified end-to-end** (contact landed via the form); the site form was **rebuilt as Brevo's native form (no iframe), moved into the right sidebar** and themed dark — live. ⚠️ *Verified limitation:* Brevo's form endpoint **silently drops fields not configured in the form** (proved by posting a `REGION` value — it saved empty), so adding a `<select name="REGION">` to our embed is **not** enough; the region field must be added in Brevo's **form editor** (no public Forms API exists among Brevo's 227 endpoints). Form-level double opt-in is likewise a UI setting; a DOI API endpoint does exist (`POST /v3/contacts/doubleOptinConfirmation`) as an alternative.
- **Distribution: Reddit + Danish communities** — post the weekly digest to r/Denmark / r/Europe / Danish FB groups with a mention back; the fastest organic follower lever, zero code risk.
- **Correction: English is NOT a bilingual mirror** — X native translation already covers comprehension; dual-language posts risk duplicate/spam flagging and double the API cost. English value lives only in the curated briefing (discoverability + original content), not as a parallel feed. (Supersedes the old "English summaries" lever below.)
- English *discoverability* within the briefing, for the international audience (see correction above; folded into the newsletter briefing)
- Analytics: track which posts drive profile visits/follows
- **Journalist / police-beat outreach & citations** — get @PolitiUpdate followed/cited by Danish police-beat journos (TV2, DR, BT, Ekstra Bladet, local papers); reply to snippet posts with the complete text where it adds value. Their replies/retweets reach a far larger readership than follow-for-speed.
- **Shareable content products (differentiation, not raw feed)** — weekly "Denmark crime wrap", notable-case depth threads, and district data-viz (weekly incident heat/trends, which only we can produce from the full dataset). Original content both drives retweets and shields against the aggregator revenue cut.
- **X SEO / discoverability** — keep consistent district names + Danish keywords (efterlysning, savnet, grundlovsforhør, anholdt) + tags; passive and compounds.
- **Same-case threading (cross-release)** — thread follow-up releases as replies to the original tweet (e.g. an "Efterlysning aflyst" cancellation replies to its "Efterlysning" appeal) instead of posting flat. *What exists:* multi-update threads on one page already post as threads, and `poster` supports `in_reply_to_tweet_id`. *Gap:* linking separate releases (different URLs) for the same case. *Scope (narrow first):* thread only "Efterlysning aflyst/afblæst" cancellations as replies to their original appeal. *Needs:* (1) a case key derived from content — district + person name/age/location, since the police don't tag releases with a case ID; (2) a DB `case_key → tweet_id` map recorded when an appeal posts; (3) reply wiring passing `in_reply_to_tweet_id` on a key match. *Risks:* false-positive linking (mitigate with conservative matching + flat-post fallback), cancellations not repeating the full person description, cancellations arriving before the appeal posts. *Recommendation:* narrow scope + conservative matching; genuine UX win but not urgent.

## Prerequisites / open items
- X API Project/App + OAuth 1.0a keys with write access
- X Premium subscription (needed for long posts; later monetization)
- **Newsletter backend: Brevo (Free plan) — DECIDED 2026-09-09** — chosen over MailerLite because MailerLite's free plan blocks API sending (its pricing FAQ: *"On Free, API and MCP access is limited and doesn't include sending"*), which our scheduled `src/newsletter` job needs; Brevo free exposes API + SMTP on all plans, unlimited contacts, 300 emails/day, forms, double opt-in, EU-based (France), GDPR-friendly. *Setup:* create Brevo account → get sending approved → sender subdomain + SPF/DKIM/DMARC → contact attribute for region → embed signup form on site (✅ live, but currently email-only — a `region` field is still pending) → build `src/newsletter` to send region-briefings via the Brevo API (mirrors the `src/digest` cron). *Trade-offs:* free plan has a "Sent with Brevo" footer; 300 emails/day cap is fine at current scale — upgrade (Starter/PAYG) or migrate to self-hosted Listmonk if we outgrow it. Web3Forms stays reserved for the site feedback form, not the list/campaign engine.
- **Domain (BLOCKER for Brevo sending)** — Brevo requires an authenticated sending domain; Gmail/Yahoo (Feb 2024) and Microsoft (May 2025) mandate it, and free-mail domains (Gmail/Yahoo) **cannot** be authenticated, so a domain must be purchased. All candidates validated AVAILABLE via registry RDAP (2026-09-09): **politiupdate.com** (recommended), **politiupdate.dk**, **politiupdate.net**, **politiupdate.io**, **politiupdate.app**, **politiupdate.news**, **politiupdate.live**, **politiupdate.eu**, **politiupdate.co**. *Plan:* register the root (e.g. `politiupdate.com`), use a **subdomain** (`mail.politiupdate.com`) as the Brevo authenticated sending domain, and (optional) point GitHub Pages at the root. *Routed to alfred for a Jira ticket / Signal reminder.*
  - *Sender DNS records (ready to paste once the domain is bought):* **Brevo code** — TXT on `mail.politiupdate.com`; **DKIM** — 2 CNAMEs (or 1 TXT) from the Brevo domain page; **DMARC** — TXT `_dmarc` = `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` (only one DMARC record allowed). Then add the sender in Brevo → Senders, and set `BREVO_SENDER_EMAIL` (e.g. `nyhedsbrev@mail.politiupdate.com`).
  - *Brevo API access (authorised IPs):* the account has **Authorised IPs** enabled — API calls return HTTP 401 *"unrecognised IP address"* unless the caller's IP is added at https://app.brevo.com/security/authorised_ips. The Hermes host (**192.74.128.119**) was added 2026-09-10; the **UmbrelOS host's IP will also need adding** when the weekly send is wired (it runs from there).
