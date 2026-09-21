#!/usr/bin/env python3
"""Verify that the staged (uncommitted) work still lands cleanly on ``origin/main``.

Why this exists
---------------
Pushing ``main`` auto-deploys (GitHub Pages + Portainer), so the staged batch is
deliberately held back for Rune's go-ahead. But two things rot while it waits:

1. **`main` moves under it.** ``src/digest`` commits each week's archive page
   straight to ``main`` (plus a "link previous week forward" edit), so a staged
   batch that touches ``website/uge/**`` can silently *revert* the digest's own
   edits if it is pushed without pulling first.
2. **A hand-maintained ritual rots too.** The correct push order lived only in a
   state-file note and in a human's memory; "run the backfill, then the suite,
   then push" is exactly the kind of list that is skipped under pressure.

So the order is executable: this script reproduces it in a **throwaway git
worktree** and reports whether it still holds.

What it does
------------
1. ``git fetch`` and report the drift (behind/ahead of ``origin/main``).
2. List the staged files (modified + untracked) and flag the ones ``origin/main``
   also touched — the revert-risk set.
3. Create a detached worktree at ``origin/main`` and copy *only* the staged files
   into it (this is the post-``git pull`` state).
4. Run ``scripts/backfill-archive-pages.py --all``: re-renders every published
   week from its own live ``digest.json``, which is what restores the digest's
   forward-pager links on any page both sides edited.
5. Run the test suite (``--ignore=tests/test_e2e.py``, coverage gate included).
6. With ``--compare-live``, diff each re-rendered archive page against the live
   served page and fail if any line was **removed** that is not a known
   template-level addition (a `<meta>`/OG/asset/signup line). Additive-only is
   the property that makes the backfill safe; it should be asserted, not eyeballed.
7. Report what the push would contain and a verdict.

It writes nothing to the real checkout, never commits and never pushes.

Usage
-----
    python scripts/preflight-push.py                  # full dry run
    python scripts/preflight-push.py --no-tests        # skip pytest (fast)
    python scripts/preflight-push.py --compare-live    # + live-page diff
    python scripts/preflight-push.py --keep            # keep the worktree
    python scripts/preflight-push.py --json
"""

from __future__ import annotations

import argparse
import collections
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_BASE_URL = "https://runestone0.github.io/PolitiUpdate"

# Paths that are never part of a push (secrets, runtime state, scratch).
EXCLUDED_PREFIXES = ("data/", ".venv/", ".git/", ".preflight", "__pycache__")

# A line may disappear from a *published* archive page only if it is a
# template-level line the backfill intentionally replaces or moves: Open
# Graph/Twitter metadata and the Brevo signup assets/block did not exist on the
# pre-template pages, and `twitter:card` is intentionally upgraded to
# `summary_large_image`. Anything else vanishing (a pager link, a nav link, a
# case item) is a regression, not a redesign.
BENIGN_REMOVED_MARKERS = (
    "<meta ",
    "<link ",
    "<script ",
    "og:",
    "twitter:",
    "description",
    "canonical",
    "sibforms",
    "digest-signup",
    "brevo",
)


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def git(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=cwd)


def staged_files() -> list[str]:
    """Modified tracked files + untracked files, minus runtime/secret paths."""
    out: list[str] = []
    for args in (("diff", "--name-only", "HEAD"), ("ls-files", "--others", "--exclude-standard")):
        proc = git(*args)
        if proc.returncode != 0:
            raise SystemExit(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
        out += [line for line in proc.stdout.splitlines() if line.strip()]
    seen: dict[str, None] = {}
    for path in out:
        if path.startswith(EXCLUDED_PREFIXES) or path == ".env" or path.startswith(".env."):
            continue
        seen.setdefault(path, None)
    return sorted(seen)


def upstream_touched() -> set[str]:
    proc = git("diff", "--name-only", "HEAD..origin/main")
    if proc.returncode != 0:
        return set()
    return {line for line in proc.stdout.splitlines() if line.strip()}


def drift() -> tuple[int, int]:
    proc = git("rev-list", "--left-right", "--count", "HEAD...origin/main")
    left, right = (proc.stdout.split() + ["0", "0"])[:2]
    return int(left), int(right)


def _benign_removal(line: str, local_text: str) -> bool:
    """A line may vanish from a published archive page only in two benign ways.

    1. **Template-level replacement** — Open Graph/Twitter metadata and the Brevo
       signup assets/block did not exist on pages published before the template
       change, and ``twitter:card`` is intentionally upgraded to
       ``summary_large_image``.
    2. **Re-flow** — the *content* of the line is still in the page, just merged
       with a neighbour (the signup script tag now shares its line with
       ``</body>``). Blank lines count as re-flow.

    Anything else vanishing — a pager link, a nav link, a case item — is a
    regression, not a redesign.
    """
    stripped = line.strip()
    if not stripped:
        return True
    if stripped in local_text:
        return True
    return any(marker in stripped.lower() for marker in BENIGN_REMOVED_MARKERS)


def compare_live(worktree: Path) -> tuple[bool, list[str]]:
    """Assert the re-rendered pages are additive vs. the live served pages."""
    problems: list[str] = []
    for page in sorted((worktree / "website" / "uge").glob("*/*/index.html")):
        year, week = page.parts[-3], page.parts[-2]
        url = f"{SITE_BASE_URL}/uge/{year}/{week}/"
        try:
            with urlopen(url, timeout=30) as resp:  # noqa: S310 (fixed https URL)
                live = resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            print(f"  ? uge {week}/{year}: live page not comparable ({exc})")
            continue
        local = page.read_text(encoding="utf-8")
        removed_raw = [ln for ln, n in
                       (collections.Counter(live.splitlines()) - collections.Counter(local.splitlines())).items()
                       for _ in range(n)]
        added = sum((collections.Counter(local.splitlines()) - collections.Counter(live.splitlines())).values())
        suspects = [ln.strip() for ln in removed_raw if not _benign_removal(ln, local)]
        status = "additive only" if not suspects else f"⚠ {len(suspects)} unexplained removed line(s)"
        print(f"  = uge {week}/{year}: +{added} / -{len(removed_raw)} lines ({status})")
        for line in suspects[:5]:
            print(f"      ⚠ removed: {line[:120]}")
        if suspects:
            problems.append(f"uge {week}/{year}: {len(suspects)} unexplained removed line(s)")
    return (not problems), problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-fetch", action="store_true", help="skip git fetch")
    parser.add_argument("--no-tests", action="store_true", help="skip the test suite")
    parser.add_argument("--compare-live", action="store_true",
                        help="diff the re-rendered pages against the live ones")
    parser.add_argument("--keep", action="store_true", help="keep the worktree for inspection")
    parser.add_argument("--json", action="store_true", help="machine-readable summary")
    args = parser.parse_args()

    report: dict = {"repo": str(REPO_ROOT)}

    if not args.no_fetch:
        fetch = git("fetch", "origin", "--quiet")
        if fetch.returncode != 0:
            print(f"! git fetch failed: {fetch.stderr.strip()}")
    ahead, behind = drift()
    report["ahead"], report["behind"] = ahead, behind
    print(f"drift: {behind} commit(s) behind origin/main, {ahead} ahead (local branch is main)")

    staged = staged_files()
    if not staged:
        print("nothing staged — the working tree matches HEAD; nothing to preflight")
        report.update({"staged": [], "ok": True, "note": "nothing staged"})
        if args.json:
            print(json.dumps(report))
        return 0
    overlap = sorted(set(staged) & upstream_touched())
    report["staged"] = staged
    report["overlap"] = overlap
    print(f"staged: {len(staged)} file(s), {sum(1 for p in staged if p.endswith('.py'))} python, "
          f"{sum(1 for p in staged if p.startswith('website/'))} website")

    tmp = Path(tempfile.mkdtemp(prefix="pu-preflight-"))
    worktree = tmp / "wt"
    worktree_added = False
    try:
        proc = git("worktree", "add", "--detach", str(worktree), "origin/main")
        if proc.returncode != 0:
            print(f"! could not create worktree at origin/main: {proc.stderr.strip()}")
            report["ok"] = False
            return 1
        worktree_added = True

        if overlap:
            print(f"revert-risk set (origin/main also edited these): {len(overlap)} file(s)")
            for path in overlap[:8]:
                print(f"  ~ {path}")
            print("  → resolved by the backfill re-rendering each published week from its live digest.json")

        copied = 0
        for rel in staged:
            source = REPO_ROOT / rel
            if not source.is_file():
                continue  # directory-only entries (e.g. a new folder) come with their files
            target = worktree / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied += 1
        print(f"worktree at origin/main ← {copied} staged file(s) copied")

        print("backfill: re-rendering published weeks from their live digest.json")
        backfill = run([sys.executable, "scripts/backfill-archive-pages.py", "--all"], cwd=worktree)
        tail = (backfill.stdout or backfill.stderr).strip().splitlines()
        for line in tail[-6:]:
            print(f"  {line}")
        report["backfill_rc"] = backfill.returncode

        live_ok, live_problems = (True, [])
        if args.compare_live:
            print("live diff: published pages vs. the served HTML")
            live_ok, live_problems = compare_live(worktree)
            report["live_problems"] = live_problems

        tests_rc: int | None = None
        tests_summary = ""
        if not args.no_tests:
            print("tests: pytest tests/ --ignore=tests/test_e2e.py")
            tests = run([sys.executable, "-m", "pytest", "tests/", "--ignore=tests/test_e2e.py", "-q"],
                        cwd=worktree)
            lines = (tests.stdout or "").strip().splitlines()
            tests_summary = next((ln for ln in reversed(lines) if "passed" in ln or "failed" in ln or "error" in ln), "")
            for line in lines[-3:]:
                print(f"  {line}")
            tests_rc = tests.returncode
        report["tests_rc"] = tests_rc
        report["tests_summary"] = tests_summary

        git("add", "-A", cwd=worktree)  # worktree-only index; not a commit, not a push
        stat = git("diff", "--cached", "--stat", "origin/main", cwd=worktree)
        stat_lines = [ln for ln in stat.stdout.splitlines() if ln.strip()]
        report["push_summary"] = stat_lines[-1].strip() if stat_lines else ""
        print(f"push would contain: {report['push_summary'] or '(nothing)'}")

        ok = report["backfill_rc"] == 0 and (not args.compare_live or live_ok) and tests_rc in (None, 0)
        report["ok"] = ok
        print("verdict: " + ("OK — the staged batch still applies in the documented order"
                             if ok else "NOT ready — see the failures above"))
    finally:
        if worktree_added and not args.keep:
            git("worktree", "remove", "--force", str(worktree))
            git("worktree", "prune")
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)
        elif worktree_added:
            print(f"worktree kept at {worktree}")

    if args.json:
        print(json.dumps(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
