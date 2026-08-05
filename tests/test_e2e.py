#!/usr/bin/env python3
"""End-to-end dry-run test of the PolitiUpdate pipeline.

Runs the full pipeline (fetch -> scrape -> format -> dedupe) without posting to X.
Tests ALL mode combinations in a single run — no env var dependency.

Usage:
    source venv/bin/activate
    python tests/test_e2e.py

    # To also test LLM summarization:
    LLM_API_KEY=sk-... LLM_ENABLED=1 python tests/test_e2e.py
"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MAX_NEW_ITEMS_PER_POLL", "3")

tmpdir = tempfile.mkdtemp(prefix="pu_test_")
os.environ["DB_PATH"] = os.path.join(tmpdir, "test.db")

from src.bot import db, fetcher, formatter, config


def fmt(text: str) -> str:
    """Render newlines as ¶ for compact single-line display."""
    return text.replace("\n", " ¶ ")


def _run_mode(
    label: str,
    post_max_chars: int,
    llm_enabled: bool,
    items: list[dict],
) -> list[dict]:
    """Run formatting for given settings, return list of formatted posts."""

    formatter.POST_MAX_CHARS = post_max_chars
    formatter.LLM_ENABLED = llm_enabled

    results: list[dict] = []

    for item_idx, raw in enumerate(items):
        title = raw["title"]
        district, thread_items = fetcher.fetch_press_release(raw["link"])

        if not thread_items:
            results.append({"item_idx": item_idx, "error": "no thread items"})
            continue

        formatted = []
        for ti in thread_items:
            post = formatter.format_post(title, district, ti["body"])
            formatted.append({
                "timestamp": ti.get("timestamp", "?"),
                "body_chars": len(ti["body"]),
                "post_chars": len(post),
                "over_limit": post_max_chars > 0 and len(post) > post_max_chars,
                "post": post,
            })

        results.append({
            "item_idx": item_idx,
            "title": title,
            "formatted": formatted,
        })

    return results


def print_mode_header(label: str, post_max_chars: int, llm_enabled: bool):
    bar = "=" * 72
    print(f"\n\n{bar}")
    short = "LLM" if llm_enabled else "truncation"
    print(f"  MODE: {label}  (POST_MAX_CHARS={post_max_chars}, {short})")
    print(bar)


def print_results(label: str, results: list[dict], post_max_chars: int):
    for r in results:
        if "error" in r:
            print(f"\n  ITEM {r['item_idx']+1}: {r['error']}")
            continue

        print(f"\n  {'─' * 68}")
        print(f"  ITEM {r['item_idx']+1}: {r['title']}")

        for i, fp in enumerate(r["formatted"]):
            tag = "MAIN" if i == 0 else f"REPLY#{i}"
            ov = ""
            if fp["over_limit"]:
                ov = f"  ⚠ OVER {post_max_chars} — would be condensed/truncated"
            print(f"  {tag}  [{fp['timestamp']}]  "
                  f"body={fp['body_chars']}ch  →  post={fp['post_chars']}ch{ov}")
            print(f"  │ {fmt(fp['post'])}")


def cross_compare(name_a: str, results_a: list[dict],
                  name_b: str, results_b: list[dict],
                  post_max_chars: int):
    """Show side-by-side size comparison between two modes."""
    bar = "=" * 72
    print(f"\n\n{bar}")
    print(f"  COMPARE: {name_a}  vs  {name_b}")
    print(f"  Posts exceeding {post_max_chars} chars in {name_a} are compared")
    print(bar)

    for ra, rb in zip(results_a, results_b):
        if "error" in ra or "error" in rb:
            continue
        for i, (fa, fb) in enumerate(zip(ra["formatted"], rb["formatted"])):
            tag = "MAIN" if i == 0 else f"REPLY#{i}"
            if fa["post_chars"] != fb["post_chars"]:
                delta = fb["post_chars"] - fa["post_chars"]
                print(f"  {tag}  {ra['title'][:50]}...")
                print(f"    {name_a}: {fa['post_chars']} chars   →   "
                      f"{name_b}: {fb['post_chars']} chars  (Δ{delta:+d})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

print("=" * 72)
print("  PolitiUpdate E2E Test (dry-run)")
print("=" * 72)

db.init_db()

# Fetch once
items = fetcher.fetch_feed()
print(f"\n  Fetched {len(items)} RSS items")

if not items:
    print("  FAIL: No items in feed")
    sys.exit(1)

# Take a small batch
batch = items[: int(os.environ["MAX_NEW_ITEMS_PER_POLL"])]
batch = [raw for raw in batch if not db.is_known(raw["guid"])]

if not batch:
    print("  All items already known — nothing to test")
    shutil.rmtree(tmpdir)
    sys.exit(0)

# ---- Mode 1: Truncation at 280 chars ----
results_trunc = _run_mode("TRUNCATION", 280, False, batch)
print_mode_header("TRUNCATION", 280, False)
print_results("TRUNCATION", results_trunc, 280)

# ---- Mode 2: Full-length (X Premium) ----
results_full = _run_mode("FULL-LENGTH (X_PRO)", 25000, False, batch)
print_mode_header("FULL-LENGTH (X_PRO)", 25000, False)
print_results("FULL-LENGTH", results_full, 25000)

# ---- Mode 3: LLM summarization (always runs with mocked API) ----
from unittest import mock

def _mock_summarize(body: str, max_chars: int) -> str:
    if len(body) <= max_chars:
        return body
    for delim in (". ", "! ", "? "):
        idx = body[:max_chars].rfind(delim)
        while idx > 20:
            after = idx + 2
            if after < len(body) and body[after].isupper():
                return body[:idx + 1]
            idx = body[:idx - 1].rfind(delim)
    last_space = body[:max_chars].rfind(" ")
    if last_space > max_chars // 2:
        return body[:last_space]
    return ""

with mock.patch("src.bot.summarizer.summarize", side_effect=_mock_summarize):
    results_llm = _run_mode("LLM SUMMARIZATION", 280, True, batch)

print_mode_header("LLM SUMMARIZATION (mock)", 280, True)
print_results("LLM", results_llm, 280)
cross_compare("TRUNCATION", results_trunc, "LLM", results_llm, 280)

# ---- Cross-compare truncation vs full-length ----
cross_compare("TRUNCATION", results_trunc, "FULL-LENGTH", results_full, 280)

# ---------------------------------------------------------------------------
# Dedupe check
# ---------------------------------------------------------------------------
for raw in batch:
    db.save_post(raw["guid"], raw["title"], "", status="posted", x_post_id="dry-run")

new_in_second = sum(1 for raw in batch if not db.is_known(raw["guid"]))

print(f"\n  Dedupe: {'PASS (0 new on second pass)' if new_in_second == 0 else f'FAIL ({new_in_second} new)'}")

shutil.rmtree(tmpdir)
print("  All checks passed.\n")
