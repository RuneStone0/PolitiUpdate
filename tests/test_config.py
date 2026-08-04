"""Tests for config.py — environment variable parsing and defaults."""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib
import src.bot.config as config


class TestDefaults:
    def test_rss_feed_url_default(self):
        assert config.RSS_FEED_URL == "https://via.ritzau.dk/rss/short-messages/latest"

    def test_poll_interval_default(self):
        assert config.POLL_INTERVAL_SECONDS == 30

    def test_post_max_chars_default(self):
        assert config.POST_MAX_CHARS in (280, 25000)

    def test_rate_limit_backoff_default(self):
        assert config.RATE_LIMIT_BACKOFF == 900

    def test_max_new_items_per_poll_default(self):
        assert config.MAX_NEW_ITEMS_PER_POLL == 5

    def test_dry_run_default(self):
        assert config.DRY_RUN is True  # conftest sets DRY_RUN=1

    def test_x_pro_default(self):
        assert config.X_PRO is False  # conftest doesn't set X_PRO

    def test_llm_disabled_default(self):
        assert config.LLM_ENABLED is False

    def test_llm_model_default(self):
        assert config.LLM_MODEL == "deepseek-chat"

    def test_llm_base_url_default(self):
        assert config.LLM_BASE_URL == "https://api.deepseek.com/v1"

    def test_llm_timeout_default(self):
        assert config.LLM_TIMEOUT == 30


class TestEnvOverrides:
    def test_dry_run_from_env(self):
        with mock.patch.dict(os.environ, {"DRY_RUN": "true"}):
            importlib.reload(config)
            assert config.DRY_RUN is True

    def test_x_pro_from_env(self):
        with mock.patch.dict(os.environ, {"X_PRO": "1"}):
            importlib.reload(config)
            assert config.X_PRO is True

    def test_llm_enabled_from_env(self):
        with mock.patch.dict(os.environ, {"LLM_ENABLED": "yes"}):
            importlib.reload(config)
            assert config.LLM_ENABLED is True

    def test_post_max_chars_override(self):
        with mock.patch.dict(os.environ, {"POST_MAX_CHARS": "500"}):
            importlib.reload(config)
            assert config.POST_MAX_CHARS == 500

    def test_x_pro_raises_post_max(self):
        with mock.patch.dict(os.environ, {"X_PRO": "1"}):
            importlib.reload(config)
            assert config.POST_MAX_CHARS == 25000
