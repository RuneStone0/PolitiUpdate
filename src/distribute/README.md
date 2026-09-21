# distribute

Generates the week's **channel kit**: paste-ready Danish drafts for the manual
distribution channels (Reddit self-post, regional Facebook-group post, X post)
from the *published* weekly digest.

## Why

Distribution is the binding constraint, not the pipeline
(`docs/growth/distribution-playbook.md`): 27 X followers ≈ zero organic reach.
Reddit is the only lever with real reach and it is **manual** (Reddit closed
self-service API app creation — no bot can post). A manual channel dies if
every week costs a writing session, so this app turns "write the week's post"
into "copy, paste, reply".

## Data source

`website/uge/{year}/{week}/digest.json` — the archive the `src/digest` app
already commits to the repo. No DB, no API key, no network, no LLM: the kit
can never disagree with what readers actually saw that week.

## Usage

```bash
python -m src.distribute                 # latest published week
python -m src.distribute --list          # published weeks available
python -m src.distribute --week 37       # a specific week
python -m src.distribute --channel reddit --stdout
python -m src.distribute --channel facebook --region Hovedstaden
```

Writes `<out>/<year>-W<week>-{reddit,facebook,x}.md` + `-summary.json`
(default `data/distribution/`, gitignored). Read-only: it never posts, never
commits, and needs no credentials.

⚠️ If `--list` does not show the newest week, the checkout is stale — the
`src/digest` app commits each week's archive straight to `main`, so
`git pull` first (or point `--published-dir` at a synced copy).

## Honesty gate

Production runs `X_PRO` unset (`POST_MAX_CHARS=280`, `LLM_ENABLED=1`), so ~68%
of releases are LLM-condensed rather than mirrored verbatim (verified against
the live container + prod DB — `docs/PLAN.md` → "Full-message posts are NOT
live"). Drafts must therefore never claim "fuld tekst"/"komplet";
`generator.assert_honest` raises at build time if a template ever does.

## Posting rules baked into the drafts

- r/Denmark rule 5: **modmail the moderators first**, then a self-post with real
  content (never a bare link), then reply the same day.
- One channel at a time, one post per group per week — that is what makes a
  channel attributable while there is no analytics.
- Links carry `utm_source` so the working channel can be identified later.
- The X draft is link-free (no $0.20 URL surcharge, no dependency on a live
  archive URL).
