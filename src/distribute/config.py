"""Configuration for the channel-kit generator (``src.distribute``).

Everything here is local/offline: the kit is built from the *already
published* weekly digest data (``website/uge/{year}/{week}/digest.json``)
that the digest app commits to the repo, so this app needs no DB, no API
key and no network.
"""

import os

# Public site base (no trailing slash). Mirrors src.digest.publisher's
# SITE_BASE_URL. The domain went live 2026-09-22, so the canonical base is now
# https://politiupdates.dk (the old github.io URLs 301 there).
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://politiupdates.dk")

# Where the digest app commits its published archives.
PUBLISHED_DIR = os.getenv("PUBLISHED_DIR", "website/uge")

# Where the paste-ready drafts are written (``data/`` is gitignored).
OUTPUT_DIR = os.getenv("DISTRIBUTION_DIR", "data/distribution")

# UTM defaults per playbook §7.3 — one source per channel so the first
# channel that works is identifiable once analytics exists.
UTM_MEDIUM = os.getenv("DISTRIBUTION_UTM_MEDIUM", "social")
