"""Tests for summarizer.py — DeepSeek API based text summarization."""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.bot.config as config  # noqa: E402
import src.bot.summarizer as summarizer  # noqa: E402


class TestSummarize:
    def test_returns_none_when_no_api_key(self):
        config.LLM_API_KEY = ""
        result = summarizer.summarize("Some text", 100)
        assert result is None

    @mock.patch("src.bot.summarizer.LLM_API_KEY", "sk-fake")
    @mock.patch("src.bot.summarizer.requests.post")
    def test_returns_condensed_text(self, mock_post):
        mock_response = mock.MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Kort tekst."}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = summarizer.summarize("En meget lang politi opdatering.", 100)
        assert result == "Kort tekst."

    @mock.patch("src.bot.summarizer.LLM_API_KEY", "sk-fake")
    @mock.patch("src.bot.summarizer.requests.post")
    def test_returns_none_on_request_failure(self, mock_post):
        import requests

        mock_post.side_effect = requests.ConnectionError("Network down")

        result = summarizer.summarize("Text", 100)
        assert result is None

    @mock.patch("src.bot.summarizer.LLM_API_KEY", "sk-fake")
    @mock.patch("src.bot.summarizer.requests.post")
    def test_returns_none_on_bad_response(self, mock_post):
        mock_response = mock.MagicMock()
        mock_response.json.return_value = {}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = summarizer.summarize("Text", 100)
        assert result is None

    @mock.patch("src.bot.summarizer.LLM_API_KEY", "sk-fake")
    @mock.patch("src.bot.summarizer.requests.post")
    def test_calls_with_correct_params(self, mock_post):
        mock_response = mock.MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Ok."}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        summarizer.summarize("Test body text.", 200)

        call_args = mock_post.call_args
        assert call_args[0][0].endswith("/chat/completions")
        assert "Authorization" in call_args[1]["headers"]
        payload = call_args[1]["json"]
        assert payload["model"] == "deepseek-chat"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert "200 tegn" in payload["messages"][1]["content"]

    @mock.patch("src.bot.summarizer.LLM_API_KEY", "sk-fake")
    @mock.patch("src.bot.summarizer.requests.post")
    def test_handles_http_error_status(self, mock_post):
        import requests

        mock_response = mock.MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "500 Server Error"
        )
        mock_post.return_value = mock_response

        result = summarizer.summarize("Text", 100)
        assert result is None
