# digest

Generates and publishes the weekly PolitiUpdate digest: a Danish-language
narrative summary of the past ISO week's police posts, categorized and
distributed to the website, a GitHub Gist, and X.

Runs as a one-shot container (`restart: "no"`), invoked on a schedule rather
than staying up like `bot`.

## Pipeline

1. **`builder`** — queries the shared SQLite DB (`posts` table, same DB as
   `bot`) for posts with `status = 'posted'` in the target week, and
   categorizes them by keyword match: `missing_person`, `witness_appeal`,
   `arrest`, `other`.
2. **`generator`** — sends the categorized data to a DeepSeek-compatible LLM
   to produce a 3-5 sentence Danish narrative summary.
3. **`gist`** — publishes `digest.json` to a GitHub Gist so the site's `/uge`
   page and front-page widget can fetch live data without a redeploy.
4. **`publisher`** — commits a static archive page
   (`website/uge/{year}/{week}/index.html` + `digest.json`) to the repo via
   the GitHub Contents API. Pushing to `main` triggers the Pages deploy.
5. **`poster`** — posts a link tweet pointing at the archive page.

If no posts are found for the target week, the run aborts after step 1
without publishing anything.

## Usage

```
python -m src.digest               # generate + publish + tweet
python -m src.digest --dry-run     # print output, skip gist/archive/tweet
python -m src.digest --week 32     # override week number (uses current year)
python -m src.digest --skip-tweet  # publish but don't post to X
```

## Configuration

See [config.py](config.py). Key environment variables:

| Variable | Purpose |
| --- | --- |
| `DB_PATH` | Path to the shared SQLite DB (same file `bot` writes to) |
| `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL` | Narrative generation |
| `GITHUB_GIST_TOKEN` | PAT with `gist` scope — publishes `digest.json` |
| `GITHUB_COMMIT_TOKEN` | PAT with `contents: write` on the repo — commits archive pages |
| `DIGEST_BASE_URL` | Public base URL for archive pages (used in the tweet link) |
| `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_SECRET` | Tweet posting |
| `DIGEST_WEEK_OVERRIDE` | Optional fixed week number, mainly for testing |

An archive-commit failure is logged but non-fatal — the run still posts the
tweet even if `publisher.commit_archive` fails.
