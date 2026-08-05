"""Integration test for posting to X.

This test actually posts to X and is skipped by default. To enable, set:

  RUN_INTEGRATION=1

and ensure the OAuth1 credentials are present in the environment.

It attempts to delete the created tweet afterwards when possible.
"""

import os
import time

import pytest

from src.bot import poster


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1",
    reason="Integration tests disabled",
)


def _get_client_and_type():
    res = poster._get_client()
    if isinstance(res, tuple):
        return res
    return res, None


def test_post_and_delete_live():
    text = f"PolitiUpdate integration test at {time.strftime('%Y-%m-%d %H:%M:%S')}"
    tweet_id = poster.post_tweet(text)
    assert tweet_id is not None

    # Try to delete the tweet to avoid leaving test data behind.
    try:
        client, client_type = _get_client_and_type()
        if client is None:
            pytest.skip("No API client available for deletion")

        # Tweepy delete_tweet expects user_auth True for OAuth1, False for OAuth2
        if client_type == "oauth2":
            client.delete_tweet(int(tweet_id), user_auth=False)
        else:
            client.delete_tweet(int(tweet_id))
    except Exception:
        # Don't fail the test if cleanup can't run; log and continue.
        pass
