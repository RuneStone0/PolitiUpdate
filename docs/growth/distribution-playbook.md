# Growth — distribution playbook

_Maintained by the daily self-improvement routine. Last updated 2026-09-12._

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

Watch list: **the account is not X-verified** while the competitor is. Premium is already
assumed in `docs/financials.md` (long posts + monetization eligibility) — if it is not
actually subscribed, long posts and the reach multiplier are both missing. Verify against the
live posting account before spending anything else.

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

## 5. Channel 4 — On-platform X (compounding, currently dead)

- 18 posts last week → 2 replies and 1 retweet total. There is no conversation to piggyback on.
- The district-prefix + Danish keyword format (efterlysning, savnet, grundlovsforhør, anholdt)
  is already implemented — that part of X SEO is done.
- Missing piece: a **mention/reply loop**. We cannot answer people who talk to the account
  today (nothing monitors mentions). Backlog item "Reply-listening bot" — read-only collection
  is safe (no posting), and it is the prerequisite for every on-platform engagement play.
- Notable cases should get one quote-post per week tagging the region — that is how a 27-follower
  account gets seen by people who do not follow it.

## 6. Ready-to-paste drafts — week 36, 2026

**A. r/Denmark modmail (only after checking the rules, English or Danish both fine):**

> Hej mods,
> Jeg driver @PolitiUpdate (og runestone0.github.io/PolitiUpdate), en uofficiel, non-kommerciel
> spejling af politiets officielle RSS-opdateringer (via Ritzau). Politiet lukkede deres egne
> X-opslag, så mange danskere ser dem ikke længere.
> Jeg vil gerne dele et **ugentligt resumé** af politiets meddelelser (én post om ugen, alle
> kilder offentlige, ingen reklame, ingen paywall, ingen affiliate-links). Er det noget I kan
> acceptere, og er der en form I foretrækker (fx tekst i selve posten, link i kommentar)?
> Mvh Rune

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
   Deploy = commit + push to `main`, then verify with
   `curl -s https://runestone0.github.io/PolitiUpdate/ | grep -c 'og:image'`.
2. **Measurement.** The site has **no analytics**, so today we cannot tell whether Reddit,
   Facebook, or the X bio actually sends traffic, nor whether the signup form converts.
   *Assessed 2026-09-12:* **self-hosting Umami on the UmbrelOS host does NOT work** for this
   site — the host is not publicly reachable, so the tracking script would never load for a
   GitHub Pages visitor. Analytics therefore requires a SaaS account; **GoatCounter free** is
   the lean pick (one email account, one script tag, no cookies, EU-friendly). Rune-only step.
3. **UTM tags** on every shared link (`?utm_source=reddit&utm_medium=social`) so the first
   channel that works is identifiable — useful the moment analytics exists, harmless before.
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
