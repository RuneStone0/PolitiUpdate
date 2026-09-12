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
  - *Progress (2026-09-10 — send path = campaigns):* the weekly send now uses Brevo **email campaigns**, not per-recipient transactional email — campaigns are the right tool for a consent-based newsletter because they auto-insert the **unsubscribe link + List-Unsubscribe header** and give open/click stats (transactional adds no unsubscribe footer). Per-region **lists** created via API: `Hovedstaden`=3, `Sjælland`=4, `Jylland`=5, `Fyn`=6, `Hele landet`=7. Because the signup form can only target ONE list, per-region membership is **synced from the REGION attribute** at send time (`sender.sync_region_lists`). Each region's campaign is created + sent immediately (`POST /emailCampaigns` → `POST /emailCampaigns/{id}/sendNow`) with the region briefing as `htmlContent` (campaigns require HTML — `generator` now emits text **and** html). A **custom unsubscribe page** attaches per campaign via the `unsubscriptionPageId` param: create one in Brevo → **Settings → Campaigns → Unsubscribe pages**, then set `BREVO_UNSUB_PAGE_ID`. (Segments cannot be created via API — 404 — hence lists, not segments.) 337 tests pass, coverage 98.3%.
  - *Progress (2026-09-11):* signup count **1/10** (contact `rtk@rtk-cv.dk`, Brevo `GET /v3/contacts`) — domain purchase / ES-2190 **not** triggered yet. Daily routine can reach the Brevo API from the Hermes host (IP already allowlisted); no threshold alert fired. Distribution (not the build) is what has to move before this reaches 10 — see `docs/growth/distribution-playbook.md`.
- **Distribution: Reddit + Danish communities** (see `docs/growth/distribution-playbook.md`) — post the weekly digest to r/Denmark / r/danmark / Danish FB groups with a mention back; the fastest organic follower lever, zero code risk. *Verified 2026-09-11:* r/Denmark rule 5 forbids **selvpromovering without prior agreement** ("uden forudgående aftale") → the play must start with a **modmail to the moderators** (draft ready in the playbook), then a self-post with real content (not a bare link), then replies in the thread. r/danmark has no sub-specific rules; city subs need a per-sub rules check. ⚠️ *2026-09-12:* Rune decided the channel runs from a **dedicated PolitiUpdate account** (now created ✅). ⛔ **The script-app/OAuth automation is dead:** Reddit **closed self-service API app creation** (Responsible Builder Policy, late 2025) — `prefs/apps`'s "create app" now only routes to the policy and creates nothing (confirmed by Rune 2026-09-12). So Reddit posting must be **manual** (modmail §6A + weekly self-post §6B, posted by Rune from the dedicated account); a **Data Access Request** is the only API path (manual review, ~2–4 wks, low odds for posting). See playbook §2 update + §9.3.
- **Distribution is the binding constraint, not the pipeline (verified 2026-09-11)** — live state: 27 X followers (22 on 2026-09-06), 1,080 posts, 69 following, **not X-verified**; the week's 18 posts drew 2 replies + 1 retweet in total; newsletter 1/10 signups. Post quality verified good (district prefix, 128–271 chars, link-free). Consequence: new funnel/routine features raise a ceiling nobody reaches — spend the next cycles on distribution + measurement, and verify whether X Premium is actually active on the posting account (financials.md assumes it; the profile shows no blue check).
- **Link previews / discoverability meta — DEPLOYED 2026-09-12; share card (og:image) staged** — no Open Graph/meta description/robots.txt/sitemap existed anywhere on the site, so every shared link rendered as a bare URL. Deployed in `3943547`: `website/index.html` (meta description + OG/Twitter card + canonical), `src/digest/publisher.py` (archive template emits the same tags), `website/robots.txt` + `website/sitemap.xml` — verified live: `og:title` in the served HTML, robots/sitemap both 200. Remaining gap found + fixed locally 2026-09-12: (a) the **already-published archives 33–36 and `/uge/` had no meta at all** (the publisher template only applies to future weeks) → backfilled; (b) there was no **`og:image`**, so every card rendered as text-only → new `website/og-image.png` (1200×630, generated by `scripts/make-og-image.py`) wired into the landing page and every archive page with `twitter:card=summary_large_image`. Guarded by a new CI gate, `tests/test_share_meta.py` (15 tests): every `website/**/*.html` must carry absolute OG/Twitter URLs and an `og:image` that resolves to a real 1200×630 PNG, and the digest template must keep emitting them. Needs commit + push (Pages deploy) + a curl re-check of the served HTML.
- **Website analytics (gap)** — there is no traffic measurement at all, so no channel can be evaluated and form conversion is unknown. Options: GoatCounter/Umami free tier (account → Rune) or self-hosted Umami on the UmbrelOS host (Docker, no third party). *Assessed 2026-09-12:* **self-hosting is not viable for this site** — a container on the UmbrelOS host is not publicly reachable, so the tracking script could never load for a visitor on GitHub Pages (it would need port-forwarding/public TLS). Therefore analytics needs a **SaaS account** (GoatCounter free is the lean option: one email account, script tag, no cookies) — that is a Rune-only step, still outstanding. **Measurement without analytics (in use now):** push one channel at a time and read the delta in Brevo signup timestamps + `api.fxtwitter.com` follower counts over the following week, logging each push window to `data/growth_metrics.jsonl` — sequential pushes make the channel attributable even without pageviews.
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
- **Domain (BLOCKER for Brevo sending)** — Brevo requires an authenticated sending domain; Gmail/Yahoo (Feb 2024) and Microsoft (May 2025) mandate it, and free-mail domains (Gmail/Yahoo) **cannot** be authenticated, so a domain must be purchased. ⚠️ *Correction 2026-09-12:* the earlier "all candidates validated AVAILABLE" note was **WRONG for `.dk`** — `rdap.org` has no `.dk` RDAP, so its HTTP 404 means "no RDAP record", not "unregistered". Verified properly: **`politiupdate.dk` is REGISTERED** (held on CSC brand-protection nameservers). `.com`/`.net`/`.org` **are** genuinely free (RDAP is authoritative for those TLDs). *Plan (superseded — see the DECISION bullet below):* register `politiupdates.dk`, use **`mail.politiupdates.dk`** as the Brevo authenticated sending subdomain, and point GitHub Pages at the apex.
  - **DECISION (2026-09-12): buy `politiupdates.dk` now** — the defer-until-+10 gate is dropped, because (a) the Reddit channel (now our top distribution lever, and **manual**) needs a credible, Danish-looking link — `runestone0.github.io/PolitiUpdate` reads as a hobby scraper to r/Denmark mods; (b) a domain is a hard prerequisite for the Brevo send regardless; (c) it's only ~$5–8/yr. ⚠️ **`politiupdate.dk` (the exact match) is TAKEN** — registered and held on **CSC** nameservers (= corporate brand-protection), so it's not realistically obtainable. `politiupdates.dk` is the pick; `politiupdate.com`/`.org` are free if a redirect is ever wanted. Register as a **private person** (a European *organization* registrant triggers a Punktum dk VAT-ID requirement).
  - **GitHub Pages custom domain (`politiupdates.dk`, apex):** A `@` → `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`; AAAA `@` → `2606:50c0:8000::153` … `::8003::153` (optional); CNAME `www` → `runestone0.github.io.` **Order matters: set the custom domain in repo Settings → Pages FIRST, then create DNS** (reverse order risks a subdomain takeover). Our Pages deploy is **Actions-based**, so **no `CNAME` file is needed** — it's ignored; the domain lives only in repo settings. Then tick **Enforce HTTPS** (can take up to 24h).
  - **Brevo sender records — EXACT values (domain added via the Brevo API 2026-09-12, id `6aa5cc3586c06de7e40ccffc`; these are the live-issued records).** The authenticated domain is the **apex `politiupdates.dk`** → send from e.g. `nyhedsbrev@politiupdates.dk`. No conflict with the website: the apex hosts the Pages `A` records *and* these TXT/CNAME records (different types).
    - TXT `@` = `brevo-code:72bc6b41dc963eedb14faa2783849b2f`
    - CNAME `brevo1._domainkey` → `b1.politiupdates-dk.dkim.brevo.com`
    - CNAME `brevo2._domainkey` → `b2.politiupdates-dk.dkim.brevo.com`
    - TXT `_dmarc` = `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com`
    After DNS propagates, confirm via `GET /v3/senders/domains` (look for `authenticated: true`), add the sender (`POST /v3/senders`), and set `BREVO_SENDER_EMAIL=nyhedsbrev@politiupdates.dk`.
  - **After the domain resolves:** update `src/digest/config.py` `DIGEST_BASE_URL` default, the OG/canonical tags, the X bio link, and these docs. Do NOT switch the base URL before the domain works — digest tweet links would point at a dead host.
  - *Brevo API access (authorised IPs):* the account has **Authorised IPs** enabled — API calls return HTTP 401 *"unrecognised IP address"* unless the caller's IP is added at https://app.brevo.com/security/authorised_ips. The Hermes host (**192.74.128.119**) was added 2026-09-10; the **UmbrelOS host's IP will also need adding** when the weekly send is wired (it runs from there).
