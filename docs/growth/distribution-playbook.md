# Growth — distribution playbook

_Maintained by the daily self-improvement routine. Last updated 2026-09-14._

**One-line thesis:** the product works and the pipeline is built; the constraint is that
**nobody sees the output** (27 X followers ≈ zero organic reach). Distribution first —
new features raise a ceiling nobody reaches.

## 1. Verified baseline (2026-09-11)

| Metric | Value | How it was verified |
| --- | --- | --- |
| X followers | **27** | public profile API `api.fxtwitter.com/PolitiUpdate` (no X creds needed) |
| Followers 5 days earlier | 22 (2026-09-06) | our own x-stats gist — +5, i.e. it does grow |
| Posts / following / joined | 1,099 / 69 / 2025-10-26 | public profile API (re-verified 2026-09-12) |
| X verified (blue check) | **no** | public profile API (`verification.verified = false`) |
| Bio website link | `https://runestone0.github.io/PolitiUpdate/` ✅ | public profile API |
| Engagement, week 36 (18 posts) | 16 posts 0 likes / 0 replies; 1 × 2 replies; 1 × 1 retweet | per-tweet fetch of the week's archive |
| Post quality | district prefix, 128–271 chars, link-free, no truncation artifacts | sampled live tweets |
| Newsletter signups | **1 / 10** (domain + ES-2190 trigger) | Brevo `GET /v3/contacts` |
| Competitor @PolitiUpdate0 | ~1,950 followers | docs/context.md (2026-08) |
| Prod bot config (2026-09-13) | **`X_PRO` unset → `POST_MAX_CHARS=280`**, `LLM_ENABLED=1` | `docker inspect bot` on the UmbrelOS host (non-secret keys only) |
| Longest posted text (7 d) | **279 chars — 0 posts over 280** (144 posted texts) | prod DB `posted_texts`, read-only |
| Releases needing condensation | **97 / 143 = 68%** exceed 280 chars before formatting | prod DB `posts.body` |
| Hard-truncation fallback | 3 / 144 = **2.1%** (trailing `…`) | prod DB `posted_texts` |
| Permanently dropped posts | 0 since 2026-09-06 (all 23 are from a 2026-09-03/04 window) | prod DB `posts.status='dropped_stale'` |
| Digest-tweet reach (weeks 35/36/37) | **8 / 9 / 8 views, 0 likes, 0 replies, 0 retweets** | `api.fxtwitter.com/PolitiUpdate/status/<id>` per tweet (checked 2026-09-14) |
| Prod bot config (re-checked 2026-09-14) | still `X_PRO` unset → `POST_MAX_CHARS=280`, `LLM_ENABLED=1`; 147 posted, longest text 279, **0 over 280** | `docker inspect bot` + prod DB (read-only, over SSH) |

Watch list — **RESOLVED 2026-09-13:** the account is not X-verified *and* the production bot
runs with `X_PRO` unset, so **full-message posts are not live**: the corpus is capped at 280
chars and **68% of releases are LLM-condensed** rather than mirrored verbatim. Premium is
assumed in `docs/financials.md`; it is not in effect. That makes the "complete text" claim in
the README/bio and the §4 journalist pitch **inaccurate until `X_PRO=1` is set** (see
`docs/PLAN.md` → "Full-message posts are NOT live"). Cheapest correction is X Premium
**Basic** (~$3/mo, includes 25k-char posts); the $8 tier is only needed for monetization
(500 followers + 5M impressions, and we are at 27).

## 2. Channel 1 — Reddit (largest reach per unit of effort, but gated)

**Rune's decision 2026-09-12: use a DEDICATED PolitiUpdate account**, not his personal one.
Same-day verification changed *how* that account has to be worked:

- **reddit.com's web UI is WAF-blocked from the Hermes/Umbrel host.** Both `www.reddit.com`
  and `old.reddit.com` return *"You've been blocked by network security"* to the browser, and
  anonymous JSON (`/r/Denmark/about.json`) returns the same 403 page. Egress IP
  `192.74.128.119`.
- **The OAuth API is reachable from the same host:** `POST /api/v1/access_token` answers
  normally (HTTP 401 on dummy credentials) — so a **script-type app + OAuth** is the working
  path for modmail and posting, *not* a logged-in browser session.
- Therefore: the **signup is a human step** (CAPTCHA, from Rune's own browser), and so is
  creating the app. After that this channel should run through the API.
- Credentials live in `/opt/data/private/reddit-politiupdate.env` — never in this repo.
- Let a brand-new account age a day or two (and subscribe to r/Denmark) before the modmail;
  a zero-age account with no history is the most likely to be filtered.
- ⚠️ **UPDATE 2026-09-12 — the OAuth/script-app plan is DEAD.** Reddit **closed self-service
  API app creation** under the *Responsible Builder Policy* (announced by u/redtaboo on
  r/redditdev, late 2025: *"Starting today, self-service access to Reddit's public data API
  will be closed... you will need to request approval before gaining access"*). In practice the
  `reddit.com/prefs/apps` **"create app" button no longer creates an app — it just routes to
  the policy** (confirmed live 2026-06-17, and by Rune 2026-09-12). So the script-app + creds
  step in ES-2203 **cannot be completed**; `/opt/data/private/reddit-politiupdate.env` stays
  unfilled by design, not by omission. The only remaining API path is a **Data Access Request**
  (manual review, ~2–4 weeks, no SLA, and posting/bot use is precisely what the policy is built
  to refuse — a read-only request has better odds). **Conclusion: Reddit posting must be
  MANUAL** (a human, in a browser) — the modmail and the weekly self-post need no app. Reading
  via RSS / `.json` is possible in principle, but reddit.com is WAF-blocked (403) from this host.

Rules fetched live 2026-09-11 from `https://www.reddit.com/r/Denmark/about/rules.json`:

- **Rule 5 (Selvpromovering):** *"Spam, selvpromovering, køb/salg, indsamlinger og referral
  links/promo koder er ikke tilladt uden forudgående aftale."* → a self-link post without
  **prior agreement with the moderators** is a removal/ban risk. **Modmail first.**
- Rule 1: Danish-language sub (EN/NO/SE tolerated).
- Rule 6: content must be about Denmark. Rule 7: headlines must be descriptive, factual,
  neutral (no clickbait).
- `r/danmark`: **no sub-specific rules** (site rules only) → lowest barrier, smaller reach.
- City subs (`r/Copenhagen`, `r/Aarhus`, `r/Odense`): rules not yet verified — check each one
  before posting. The regional week brief is the most relevant, least spam-like format there.

**Order of operations:** (1) modmail requesting permission → (2) on approval post a
**self-post with real content** (not a bare link) → (3) reply to comments the same day (a post
that gets replies reaches more people than the post itself). Never post the same text to
several subs the same day.

If the mods decline: drop the self-link and use the info-first formats (post the notable case
as plain information, cite politi.dk; answer other users' crime/case threads with the mirrored
link **only when it adds the complete text**). That is participation, not promotion — and it
still puts the handle in front of the audience.

**Own communities (`r/PolitiUpdate`, or one per region) — decision 2026-09-18: NOT now.**
Rune floated building our own subs, possibly one per region. Filed as ES-2222; the call is *no* for
now, on four grounds:
1. **An own sub unlocks no automation.** Posting is manual (§2 — Reddit closed self-service API app
   creation), so N regional subs = N manual weekly posts *plus* N moderation queues for Rune.
2. **Creation is gated, and u/PolitiUpdate is young.** Reddit effectively requires ~30 days of
   account age + ~50–100 combined karma + verified email + a clean record (thresholds unpublished and
   adaptive), so the gate would not clear until roughly mid-October at the earliest.
3. **Empty subs have no reach.** Reddit does not surface brand-new tiny communities; an own sub starts
   at zero and only grows from traffic we would have to bring from somewhere we don't yet reach.
4. **A dozen regional subs created from one account is a spam-farm signature.** It risks the account,
   and the account *is* the distribution asset.
*Do instead (already the plan):* r/Denmark modmail (§6A) → regional week briefs into **existing** city
subs one at a time → r/danmark (no sub-specific rules) → Facebook groups (§3) → the owned channels
(Brevo newsletter + `politiupdates.dk`).
*Revisit when:* the account has cleared the age/karma gate **and** the existing-sub strategy is
already producing replies — then a single, non-regional `r/PolitiUpdate` could serve as an owned home
for the full text (still no automation, still manual). Per-region subs stay not worth it even then:
they fragment a small audience and multiply the manual load.

## 3. Channel 2 — Danish Facebook groups

Local news groups are where the district-relevant posts actually spread (one district per post
is a natural fit — this is exactly the regional segmentation the newsletter already models).

- Target: local "nyt i <by/område>" groups, one group at a time, starting with the districts
  that produce the most content.
- Post the **regional** week brief (København / Sjælland / Jylland / Fyn), never the national
  one, and never more than once a week per group.
- Read each group's rules first (many ban links); a screenshot-free text post with the link in
  a comment is usually tolerated.
- No automation: this must be a human posting from a human account.

## 4. Channel 3 — Journalist / citation outreach

Per `docs/context.md`: their reply/retweet reaches far more people than any follow-for-speed
pitch. Method, not blasting:

- Monitor Danish police-beat coverage (TV2, DR, BT, Ekstra Bladet, Jyllands-Posten, TV2
  regional, SN.dk local editions). When a story matches a release we mirrored **before** the
  outlet published, reply/quote with the mirror link — the value is the complete text and the
  timestamp, not our opinion.
- Keep it rare and useful (a handful per week), link-free posts become link-replies (the $0.20
  URL surcharge applies per post — budget it, don't do it in bulk).
- Newsrooms also take tips through their own tip forms; use them when our dataset shows a
  pattern (e.g. a district with a spike) — that is original reporting only we can produce.
- Verify each handle before sending; never fabricate addresses or mass-mail.
- ⚠️ **Honesty gate (2026-09-13):** until `X_PRO=1` is live in production, do **not** pitch
  "the complete text" — 68% of releases are LLM-condensed to ≤280 chars today (§1, PLAN).
  Sell what is actually true: 30-second polling, all 14 districts, a searchable archive, and a
  timestamped mirror. Claiming completeness we don't deliver is exactly the kind of
  over-claim that kills a newsroom's trust on first contact.

## 5. Channel 4 — On-platform X (compounding, currently dead)

- 18 posts last week → 2 replies and 1 retweet total. There is no conversation to piggyback on.
- The district-prefix + Danish keyword format (efterlysning, savnet, grundlovsforhør, anholdt)
  is already implemented — that part of X SEO is done.
- Missing piece: a **mention/reply loop**. We cannot answer people who talk to the account
  today (nothing monitors mentions). Backlog item "Reply-listening bot" — read-only collection
  is safe (no posting), and it is the prerequisite for every on-platform engagement play.
- Notable cases should get one quote-post per week tagging the region — that is how a 27-follower
  account gets seen by people who do not follow it.

## 6. Ready-to-paste drafts

**Generated since 2026-09-14:** the Reddit self-post (B), the Facebook regional post (C) and
the X post (D) now come out of `python -m src.distribute` — it reads the published week
archive and writes `data/distribution/<year>-W<week>-{reddit,facebook,x}.md` (week 37 kit
already generated). Don't hand-write them again: to change the wording, change the template
in `src/distribute/generator.py`, whose honesty gate then covers the change. The drafts
below stay as the reference for *why* each channel reads the way it does; their week-36
numbers are historical.

**A. r/Denmark modmail — one-time, sent manually by Rune (only after checking the rules).**

⚠️ **Canonical text is NOT kept here.** The single source of truth for anything Rune sends is
`/opt/data/profiles/alfred/politiupdate/modmail-rdenmark-draft.md` (owned by **Alfred**, outside
this repo). **That copy wins on any conflict** — do not re-add a hand-maintained copy here. If a
repo copy is wanted for git history, generate/check it against Alfred's file; never edit it
independently.
Alfred's copy carries the vetted wording *plus* additions this repo's old duplicate lacked: an
explicit "unofficial, not the police" line, a disclosure that the summary is machine-drafted, and a
**domain-first** sequence (stand up `politiupdates.dk`, swap the link, verify it resolves to *our*
content, *then* send). It also flags two lines as Rune's decision.

**B. r/Denmark self-post (on approval — self-post, not a bare link):**

> **Ugens overblik: 18 opdateringer fra politiet i uge 36**
>
> Politiet har lukket deres egne X-opslag, men publicerer fortsat alt via deres officielle RSS
> (via Ritzau). Her er ugens 18 meddelelser samlet — blandt andet:
> - Efterlysning af en savnet person fra Åbenrå (fortsat ikke fundet)
> - 59-årig mand sigtet for brandstiftelse i Bramming — løsladt, sigtelsen opretholdes
> - Politibåd i sammenstød med en civil båd ved Middelgrundsfortet — to personer til Rigshospitalet
>
> Fuldt overblik (opdelt på distrikt og kategori): <link til uge-arkivet>
> Kilden er politiets egen RSS-feed — uofficielt projekt uden tilknytning til politiet.

**C. Facebook group (regional variant, København example):**

> Ugens politikort for København og omegn: politiet har haft 7 opdateringer i uge 36 —
> bl.a. sammenstødet mellem politiets båd og en civil båd ved Middelgrundsfortet.
> Har samlet dem her: <link> (uofficielt projekt, kilden er politiets egen RSS-feed).

**D. X quote-post (notable case, once a week):**

> Ugen i København: <case>. Alle politiets meddelelser fra byen samlet her →
> @PolitiUpdate

## 7. Pre-flight before any share push

1. **Link previews.** ✅ **Deployed 2026-09-12** (commit `3943547`): landing page +
   digest-archive template carry meta description, Open Graph/Twitter card and canonical;
   `robots.txt`/`sitemap.xml` are live. ⚠️ Two gaps found on 2026-09-12 and fixed locally
   (awaiting the next push):
   - archives **33–36 and `/uge/` had no meta at all** — the publisher template only applies
     to *future* weeks, so every already-published week page still rendered as a bare link;
     the five existing pages are backfilled now.
   - **no `og:image` existed**, so every card rendered text-only. Added
     `website/og-image.png` (1200×630, regenerable with `scripts/make-og-image.py`) and
     `twitter:card=summary_large_image` everywhere.
   - A new CI gate (`tests/test_share_meta.py`) fails if any published page loses its OG
     metadata, uses a relative URL, points `og:image` at a missing file, or the card stops
     being a 1200×630 PNG.
   - **the sitemap was hand-maintained and had rotted** (found 2026-09-17): week 37 was
     published 2026-09-13 and the live `sitemap.xml` still listed only weeks 33–36 four days
     later, so the newest archive was never announced to crawlers — and because
     `scripts/backfill-archive-pages.py` discovers weeks *from* that file, the stale list also
     hid the one week that needed re-rendering. `src/digest` now writes the sitemap on every
     run (`publisher.update_sitemap`, additive + idempotent), the backfill probes past the
     newest listed week, and `tests/test_sitemap.py` fails if a published week is unlisted.
   Deploy = commit + push to `main`, then verify with
   `curl -s https://runestone0.github.io/PolitiUpdate/ | grep -c 'og:image'`.
   ⚠️ **Pull before pushing** — `src/digest` commits archive pages straight to `main` every
   Sunday, so the local tree goes stale and the pending share-card work touches the same
   week-36/37 files. The sequence is no longer a note to remember: **`python
   scripts/preflight-push.py --compare-live`** performs it in a throwaway git worktree
   (fetch → worktree at `origin/main` → copy only the staged files → `backfill-archive-pages.py
   --all` → full suite → per-page diff against the *served* HTML) and exits non-zero if the
   batch would revert a published page or fail the gate. Run it before asking for the push
   go-ahead, and paste its output as the evidence. *First green run 2026-09-18:* 36 files /
   +3028 lines, weeks 33–37 additive-only vs. live, 426 passed + 1 skipped, coverage 98.32%.
2. **Measurement.** The site has **no analytics**, so today we cannot tell whether Reddit,
   Facebook, or the X bio actually sends traffic, nor whether the signup form converts.
   *Assessed 2026-09-12:* **self-hosting Umami on the UmbrelOS host does NOT work** for this
   site — the host is not publicly reachable, so the tracking script would never load for a
   GitHub Pages visitor. Analytics therefore requires a SaaS account; **GoatCounter free** is
   the lean pick (one email account, one script tag, no cookies, EU-friendly). Rune-only step.
3. **UTM tags** on every shared link — ✅ *implemented 2026-09-14* in the channel kit
   (`src/distribute` stamps `utm_source=<channel>&utm_medium=social&utm_campaign=uge<week>`
   on the Reddit/Facebook links), so the first channel that works is identifiable once
   analytics exists — harmless before it does.
4. **Tracked image asset** ✅ staged 2026-09-12 — `og:image` (1200×630) now exists and is
   wired in (see §7.1).

## 8. Measurement & cadence

Per run, append to `data/growth_metrics.jsonl`: date, followers, signups, share-push status.
Channel rule: two attempts with no measurable effect → drop the channel and say so out loud.

**Attribution while there is no analytics (adopted 2026-09-12):** push **one channel at a
time** and log the push window (start date, channel, exact copy) in the same metrics file.
Read the effect from two public signals only: the Brevo contact list (`GET /v3/contacts` →
`createdAt` timestamps) and `api.fxtwitter.com/PolitiUpdate` followers. Sequential pushes make
a channel attributable without pageviews; a channel that produces **no** new contact and no
follower movement in its window is dropped, not "kept warm".

## 9. Asks (things only Rune can do)

1. ~~Which account posts to Reddit~~ — **DECIDED 2026-09-12: a dedicated PolitiUpdate
   account.** Remaining human steps (blocked on Rune's own browser, see §2): create the
   account (username candidates in order: `PolitiUpdate`, `PolitiUpdateDK`, `politiupdate_dk`),
   then a **script**-type app at `reddit.com/prefs/apps`, and paste both values into
   `/opt/data/private/reddit-politiupdate.env`.
2. ~~Approve deploying the staged link-preview/meta changes~~ — **APPROVED and DEPLOYED
   2026-09-12** (commit `3943547`): `og:title` verified in the served HTML, `robots.txt` and
   `sitemap.xml` both 200.
3. **Reddit channel unblock** (routed to Alfred 2026-09-12; ⚠️ **re-scoped 2026-09-12**): the
   **account is created ✅**, but the **script app cannot be created** — Reddit closed
   self-service API app creation (see the §2 update). ES-2203 as written (script app + client
   id/secret handover) is therefore **not executable**. Remaining realistic path = **manual
   posting**: Rune posts the r/Denmark modmail (§6A) and the weekly self-post (§6B) from the
   dedicated account — no app, no API. Optionally file a **Data Access Request** as a separate,
   low-priority ticket (low odds for posting, ~2–4 weeks).
4. **Staged share-card push** — `og:image` + the archive meta backfill are committed-ready but
   local; needs the same go-ahead + push as item 2, then a curl re-check.
5. **Analytics account** (GoatCounter free — see §7.2) whenever Rune wants channel-level truth;
   until then §8's sequential attribution is the method.
6. **X Premium Basic for full-message posts** (NEW 2026-09-13, routed to Alfred): production
   runs `X_PRO` unset, so posts are capped at 280 chars and 68% of releases are LLM-condensed
   (§1). Basic (~$3/mo, web) includes 25k-char posts; after subscribing I set `X_PRO=1` in the
   bot env on the UmbrelOS host and re-verify a real >280-char post. Without this, every
   "complete text / full message" claim we make to Reddit mods, journalists and the newsletter
   list is false.
7. **Domain `politiupdates.dk`** (ES-2190; ⚠️ re-verified **still unregistered** 2026-09-14 —
   `politiupdates.dk` returns no A record and HTTPS is unreachable) — one purchase unblocks the
   newsletter send (Brevo sender `authenticated=false`) *and* gives the Reddit channel a
   credible Danish link instead of the github.io URL. The DNS/Brevo values are recorded in
   `docs/PLAN.md`; the code side is one switch (`DIGEST_BASE_URL` + OG/canonical + the X bio
   link), plus `--site-base` for the channel kit.
   - ⚠️ **Verified 2026-09-19 against the live Brevo API: this is a HARD blocker, not a
     nicety.** `POST /v3/emailCampaigns` with sender `nyhedsbrev@politiupdates.dk` returns
     **HTTP 400 `invalid_parameter` "Sender is invalid / inactive"** — Brevo refuses to create
     the campaign at all, so no briefing can be sent until the domain/sender exists. Everything
     else on the send path is now rehearsed green against the live API (contact routing,
     list-membership sync + read-back) by
     `politiupdate_newsletter_rehearsal.py`; only the final `sendNow` is unexercised.
   - The only active Brevo sender today is id 1 `rtk@rtk-cv.dk` under the name **"BrilliantR"**
     — another project's sender identity; do not reuse it for PolitiUpdate, and do not rename it
     in place.
