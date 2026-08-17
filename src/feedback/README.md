# feedback

Posts a monthly feedback-request tweet asking followers what they like about
@PolitiUpdate and what could be better. Drives engagement and surfaces what
followers value (speed, coverage, format, etc.) — see the "User feedback
collection" backlog item in [docs/PLAN.md](../../docs/PLAN.md).

Runs as a one-shot container (`restart: "no"`), invoked on a schedule rather
than staying up like `bot`.

## Schedule: first Saturday of the month, 18:00 Danish time

Cron can't express "first Saturday of the month" or a DST-aware local time
directly, so `main.py` decides for itself whether it's actually the right
moment — mirroring how [src/notify/loop.py](../notify/loop.py) self-schedules
its daily/weekly jobs. The trigger (host cron, Portainer, etc.) is expected to
fire more often than the app actually posts; see the crontab example in the
root [README](../../README.md#scheduling-batch-jobs).

## Usage

```
python -m src.feedback                 # post if it's the scheduled time, else skip
python -m src.feedback --force         # post now, skipping the scheduling gate
python -m src.feedback --dry-run       # print output, skip posting and the gate
python -m src.feedback --month 2026-08 # override year-month, skipping the gate (mainly for testing)
```

A run for a year-month that's already been posted (tracked in
`FEEDBACK_STATE_PATH`) is skipped, so a misfiring schedule or manual retry
won't double-post or hit X's duplicate-content rejection.

## Configuration

See [config.py](config.py). Key environment variables:

| Variable | Purpose |
| --- | --- |
| `X_API_KEY` / `X_API_SECRET` / `X_ACCESS_TOKEN` / `X_ACCESS_SECRET` | Tweet posting (same OAuth 1.0a credentials as `src/bot` and `src/digest`) |
| `FEEDBACK_TIMEZONE` | IANA timezone for the scheduling gate (default: `Europe/Copenhagen`) |
| `FEEDBACK_HOUR_LOCAL` | Local hour the post fires at/after, on the first Saturday of the month (default: `18`) |
| `FEEDBACK_STATE_PATH` | Where the last-posted year-month is tracked (default: `data/feedback_state.json`) |
| `FEEDBACK_MONTH_OVERRIDE` | Optional fixed year-month (e.g. `2026-08`), skips the scheduling gate, mainly for testing |
