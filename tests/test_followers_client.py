"""Tests for src.followers.client — X API auth (OAuth 1.0a / OAuth 2.0)."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import src.followers.client as client  # noqa: E402


class TestGetClientOAuth1:
    def test_uses_oauth1_when_all_creds_present(self):
        with mock_all(client, X_API_KEY="k", X_API_SECRET="s", X_ACCESS_TOKEN="t", X_ACCESS_SECRET="a"):
            c, client_type = client.get_client()
        assert client_type == "oauth1"
        assert c is not None


class TestGetClientErrors:
    def test_raises_without_any_credentials(self):
        with mock_all(
            client,
            X_API_KEY="", X_API_SECRET="", X_ACCESS_TOKEN="", X_ACCESS_SECRET="",
            X_CLIENT_ID="", X_CLIENT_SECRET="",
        ):
            with pytest.raises(RuntimeError, match="not configured"):
                client.get_client()


class TestGetClientOAuth2:
    def test_uses_refresh_token_from_env(self, monkeypatch):
        with mock_all(
            client,
            X_API_KEY="", X_API_SECRET="", X_ACCESS_TOKEN="", X_ACCESS_SECRET="",
            X_CLIENT_ID="cid", X_CLIENT_SECRET="csec", X_REFRESH_TOKEN="rtok",
        ):
            monkeypatch.setattr(
                client,
                "_refresh_access_token",
                lambda rt: {"access_token": "newtok", "expires_in": 7200, "refresh_token": "rtok2"},
            )
            saved = {}
            monkeypatch.setattr(client, "_save_tokens", lambda tokens: saved.update(tokens))

            c, client_type = client.get_client()

        assert client_type == "oauth2"
        assert saved["access_token"] == "newtok"

    def test_loads_and_refreshes_expired_file_token(self, monkeypatch, tmp_path):
        token_file = tmp_path / "tokens.json"
        import json

        token_file.write_text(
            json.dumps(
                {
                    "access_token": "old",
                    "refresh_token": "rtok",
                    "expires_in": 100,
                    "obtained_at": int(time.time()) - 1000,
                }
            )
        )
        with mock_all(
            client,
            X_API_KEY="", X_API_SECRET="", X_ACCESS_TOKEN="", X_ACCESS_SECRET="",
            X_CLIENT_ID="cid", X_CLIENT_SECRET="csec", X_REFRESH_TOKEN="",
            X_TOKEN_FILE=str(token_file),
        ):
            monkeypatch.setattr(
                client,
                "_refresh_access_token",
                lambda rt: {"access_token": "refreshed", "expires_in": 7200},
            )
            saved = {}
            monkeypatch.setattr(client, "_save_tokens", lambda tokens: saved.update(tokens))

            c, client_type = client.get_client()

        assert client_type == "oauth2"
        assert saved["access_token"] == "refreshed"

    def test_reuses_unexpired_file_token(self, tmp_path):
        token_file = tmp_path / "tokens.json"
        import json

        token_file.write_text(
            json.dumps(
                {
                    "access_token": "still-good",
                    "refresh_token": "rtok",
                    "expires_in": 7200,
                    "obtained_at": int(time.time()),
                }
            )
        )
        with mock_all(
            client,
            X_API_KEY="", X_API_SECRET="", X_ACCESS_TOKEN="", X_ACCESS_SECRET="",
            X_CLIENT_ID="cid", X_CLIENT_SECRET="csec", X_REFRESH_TOKEN="",
            X_TOKEN_FILE=str(token_file),
        ):
            c, client_type = client.get_client()

        assert client_type == "oauth2"

    def test_raises_when_token_file_missing(self, tmp_path):
        missing = tmp_path / "missing.json"
        with mock_all(
            client,
            X_API_KEY="", X_API_SECRET="", X_ACCESS_TOKEN="", X_ACCESS_SECRET="",
            X_CLIENT_ID="cid", X_CLIENT_SECRET="csec", X_REFRESH_TOKEN="",
            X_TOKEN_FILE=str(missing),
        ):
            with pytest.raises(RuntimeError, match="token file not found"):
                client.get_client()


def mock_all(mod, **overrides):
    """Context manager patching several module attributes at once."""
    from contextlib import ExitStack
    from unittest import mock

    stack = ExitStack()
    for name, value in overrides.items():
        stack.enter_context(mock.patch.object(mod, name, value))
    return stack
