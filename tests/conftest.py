"""Shared fixtures for all tests."""

import os
import sys
import tempfile
import shutil
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("DRY_RUN", "1")
os.environ.setdefault("X_API_KEY", "fake-key")
os.environ.setdefault("X_API_SECRET", "fake-secret")
os.environ.setdefault("X_ACCESS_TOKEN", "fake-token")
os.environ.setdefault("X_ACCESS_SECRET", "fake-secret-token")

import src.bot.config as config  # noqa: E402
import src.bot.formatter as formatter  # noqa: E402


@pytest.fixture(autouse=True)
def reset_config():
    """Ensure clean config state before each test."""
    config.POST_MAX_CHARS = config.X_PRO and 25000 or 280
    config.LLM_ENABLED = False
    formatter.POST_MAX_CHARS = config.POST_MAX_CHARS
    formatter.LLM_ENABLED = False


@pytest.fixture
def temp_db():
    """Provide a temporary database path and clean up afterwards."""
    tmpdir = tempfile.mkdtemp(prefix="pu_test_db_")
    db_path = os.path.join(tmpdir, "test.db")
    yield db_path
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_rss_entry():
    """Return a dict matching what fetch_feed returns."""
    return {
        "guid": "https://via.ritzau.dk/pressemeddelelse/12345/test",
        "title": "Test politi update",
        "link": "https://via.ritzau.dk/pressemeddelelse/12345/test",
        "pub_date": "Mon, 03 Aug 2026 14:00:00 GMT",
    }


@pytest.fixture
def sample_thread_items():
    """Return sample thread items as returned by _extract_thread_items."""
    return [
        {
            "body": "Seneste opdatering: personen er fundet.",
            "timestamp": "3.8.2026 23:50:26 CEST",
            "district": "Sydsjællands og Lolland-Falsters Politi",
        },
        {
            "body": "Vi leder efter en 78-årig mand. Kontakt politiet på 114.",
            "timestamp": "3.8.2026 21:28:59 CEST",
            "district": "Sydsjællands og Lolland-Falsters Politi",
        },
    ]


@pytest.fixture
def sample_html_with_thread():
    """Return HTML matching the actual press release page structure."""
    return """
    <html>
    <head><title>Test Update | Sydsjællands og Lolland-Falsters Politi</title></head>
    <body>
      <div class="short-message-thread">
        <div class="sc-gmPhUn cpoevv">
          <h1>Test Update</h1>
          <div class="thread-item">
            <p class="sc-gEvEer tGNaa">3.8.2026 23:50:26 CEST | Sydsjællands og Lolland-Falsters Politi</p>
            <div class="sc-aXZVg jdSwMh">
              <div><p>Seneste opdatering: personen er fundet.</p></div>
            </div>
          </div>
          <div class="thread-item">
            <p class="sc-gEvEer tGNaa">3.8.2026 21:28:59 CEST | Sydsjællands og Lolland-Falsters Politi</p>
            <div class="sc-aXZVg jdSwMh">
              <div><p>Vi leder efter en 78-årig mand.</p><p>Kontakt politiet på 114.</p></div>
            </div>
          </div>
        </div>
      </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_html_no_thread():
    """Return HTML without the thread structure."""
    return """
    <html>
    <head><title>Test | Politi</title></head>
    <body><p>Nothing here.</p></body>
    </html>
    """
