"""Configuration for the channel-kit generator (``src.distribute``).

Everything here is local/offline: the kit is built from the *already
published* weekly digest data (``website/uge/{year}/{week}/digest.json``)
that the digest app commits to the repo, so this app needs no DB, no API
key and no network.
"""

import os

# Public site base (no trailing slash). Mirrors src.digest.publisher's
# SITE_BASE_URL; switches to https://politiupdates.dk when the domain is live.
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://runestone0.github.io/PolitiUpdate")

# Where the digest app commits its published archives.
PUBLISHED_DIR = os.getenv("PUBLISHED_DIR", "website/uge")

# Where the paste-ready drafts are written (``data/`` is gitignored).
OUTPUT_DIR = os.getenv("DISTRIBUTION_DIR", "data/distribution")

# UTM defaults per playbook §7.3 — one source per channel so the first
# channel that works is identifiable once analytics exists.
UTM_MEDIUM = os.getenv("DISTRIBUTION_UTM_MEDIUM", "social")
