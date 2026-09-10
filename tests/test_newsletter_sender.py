"""Tests for the Brevo sender (src/newsletter/sender.py).

Covers the gating logic (no subscribers / dry-run / missing credentials) and the
real HTTP dispatch + contact-fetch paths, mocked so nothing touches the network.
"""

from unittest import mock

import pytest

from src.newsletter import config as nconfig
from src.newsletter import sender


def _mock_response(status=200, payload=None):
    resp = mock.MagicMock()
    resp.status_code = status
    resp.json.return_value = payload or {}
    return resp


@pytest.fixture
def set_creds(monkeypatch):
    monkeypatch.setattr(nconfig, "BREVO_API_KEY", "test-key")
    monkeypatch.setattr(nconfig, "BREVO_SENDER_EMAIL", "nyhedsbrev@mail.politiupdate.com")
    monkeypatch.setattr(nconfig, "BREVO_SENDER_NAME", "PolitiUpdate")


def test_send_region_no_subscribers_is_noop():
    res = sender.send_region("Jylland", [], "subj", "text")
    assert res["sent"] == 0
    assert res["note"] == "no-subscribers"


def test_send_region_dry_run_previews_without_network():
    res = sender.send_region("Jylland", ["a@example.com"], "subj", "text", dry_run=True)
    assert res["dry_run"] is True
    assert res["sent"] == 1


def test_send_region_requires_api_key(monkeypatch):
    monkeypatch.setattr(nconfig, "BREVO_API_KEY", "")
    with pytest.raises(RuntimeError, match="BREVO_API_KEY"):
        sender.send_region("Jylland", ["a@example.com"], "subj", "text")


def test_send_region_requires_sender_email(monkeypatch):
    monkeypatch.setattr(nconfig, "BREVO_API_KEY", "k")
    monkeypatch.setattr(nconfig, "BREVO_SENDER_EMAIL", "")
    with pytest.raises(RuntimeError, match="BREVO_SENDER_EMAIL"):
        sender.send_region("Jylland", ["a@example.com"], "subj", "text")


def test_brevo_send_one_email_per_recipient(set_creds):
    resp = _mock_response(payload={"messageId": "msg-1"})
    with mock.patch("src.newsletter.sender.requests.post", return_value=resp) as post:
        result = sender._brevo_send(
            "Jylland", ["a@example.com", "b@example.com"], "subj", "text"
        )

    assert result["sent"] == 2
    assert post.call_count == 2
    # Each call targets exactly one recipient (privacy — no cross-exposure).
    first_payload = post.call_args_list[0].kwargs["json"]
    assert first_payload["to"] == [{"email": "a@example.com"}]
    assert first_payload["sender"]["email"] == "nyhedsbrev@mail.politiupdate.com"
    assert first_payload["sender"]["name"] == "PolitiUpdate"
    assert first_payload["subject"] == "subj"
    assert first_payload["textContent"] == "text"
    assert post.call_args_list[0].args[0].endswith("/v3/smtp/email")


def test_brevo_send_uses_api_key_header(set_creds):
    resp = _mock_response(payload={"messageId": "msg-1"})
    with mock.patch("src.newsletter.sender.requests.post", return_value=resp) as post:
        sender._brevo_send("Jylland", ["a@example.com"], "subj", "text")
    assert post.call_args.kwargs["headers"]["api-key"] == "test-key"


def test_fetch_region_contacts_filters_by_region_attribute(set_creds):
    page = _mock_response(
        payload={
            "contacts": [
                {"email": "a@example.com", "attributes": {"REGION": "Jylland"}},
                {"email": "b@example.com", "attributes": {"REGION": "Jylland"}},
            ],
            "count": 2,
        }
    )
    with mock.patch("src.newsletter.sender.requests.get", return_value=page) as get:
        emails = sender.fetch_region_contacts("Jylland")

    assert emails == ["a@example.com", "b@example.com"]
    params = get.call_args.kwargs["params"]
    assert params["filter"] == 'equals(REGION,"Jylland")'
    assert params["limit"] == 1000
    assert params["offset"] == 0


def test_fetch_region_contacts_paginates(set_creds):
    page1 = _mock_response(payload={"contacts": [{"email": f"u{i}@x.dk"} for i in range(3)], "count": 5})
    page2 = _mock_response(payload={"contacts": [{"email": f"u{i}@x.dk"} for i in range(3, 5)], "count": 5})
    with mock.patch(
        "src.newsletter.sender.requests.get", side_effect=[page1, page2]
    ) as get:
        emails = sender.fetch_region_contacts("Jylland")

    assert len(emails) == 5
    assert get.call_count == 2
    assert get.call_args_list[1].kwargs["params"]["offset"] == 3


def test_fetch_region_contacts_requires_key(monkeypatch):
    monkeypatch.setattr(nconfig, "BREVO_API_KEY", "")
    with pytest.raises(RuntimeError, match="BREVO_API_KEY"):
        sender.fetch_region_contacts("Jylland")
