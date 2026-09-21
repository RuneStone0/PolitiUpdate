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


def test_send_region_campaign_dry_run_skips_network(set_creds):
    with mock.patch("src.newsletter.sender.requests.post") as post:
        res = sender.send_region_campaign("Jylland", "subj", "<p>x</p>", dry_run=True)
    assert res["dry_run"] is True
    assert res["sent"] is False
    assert res["list_id"] == nconfig.BREVO_REGION_LISTS["Jylland"]
    assert post.call_count == 0


def test_send_region_campaign_requires_api_key(monkeypatch):
    monkeypatch.setattr(nconfig, "BREVO_API_KEY", "")
    monkeypatch.setattr(nconfig, "BREVO_SENDER_EMAIL", "nyhedsbrev@mail.politiupdate.com")
    with pytest.raises(RuntimeError, match="BREVO_API_KEY"):
        sender.send_region_campaign("Jylland", "subj", "<p>x</p>")


def test_send_region_campaign_requires_sender_email(monkeypatch):
    monkeypatch.setattr(nconfig, "BREVO_API_KEY", "k")
    monkeypatch.setattr(nconfig, "BREVO_SENDER_EMAIL", "")
    with pytest.raises(RuntimeError, match="BREVO_SENDER_EMAIL"):
        sender.send_region_campaign("Jylland", "subj", "<p>x</p>")


def test_send_region_campaign_unmapped_region_raises(set_creds):
    with pytest.raises(RuntimeError, match="No Brevo list mapped"):
        sender.send_region_campaign("Nordpolen", "subj", "<p>x</p>")


def test_send_region_campaign_creates_then_sends(set_creds):
    created = _mock_response(status=201, payload={"id": 42})
    sent = _mock_response(status=204)
    with mock.patch(
        "src.newsletter.sender.requests.post", side_effect=[created, sent]
    ) as post:
        res = sender.send_region_campaign("Jylland", "subj", "<p>x</p>", name="nm")

    assert res["campaign_id"] == 42
    assert res["sent"] is True
    assert post.call_count == 2
    # 1) create the campaign targeting the region list
    assert post.call_args_list[0].args[0].endswith("/v3/emailCampaigns")
    payload = post.call_args_list[0].kwargs["json"]
    assert payload["name"] == "nm"
    assert payload["subject"] == "subj"
    assert payload["htmlContent"] == "<p>x</p>"
    assert payload["recipients"] == {"listIds": [nconfig.BREVO_REGION_LISTS["Jylland"]]}
    assert payload["sender"]["email"] == "nyhedsbrev@mail.politiupdate.com"
    # 2) send it immediately
    assert post.call_args_list[1].args[0].endswith("/v3/emailCampaigns/42/sendNow")
    assert post.call_args_list[1].kwargs["headers"]["api-key"] == "test-key"


def test_send_region_campaign_attaches_unsub_page(set_creds, monkeypatch):
    monkeypatch.setattr(nconfig, "BREVO_UNSUB_PAGE_ID", "unsub-1")
    created = _mock_response(status=201, payload={"id": 7})
    sent = _mock_response(status=204)
    with mock.patch("src.newsletter.sender.requests.post", side_effect=[created, sent]) as post:
        sender.send_region_campaign("Fyn", "s", "<p>x</p>")
    assert post.call_args_list[0].kwargs["json"]["unsubscriptionPageId"] == "unsub-1"


def test_sync_region_lists_batches_contacts(set_creds):
    page = _mock_response(
        payload={"contacts": [{"email": f"u{i}@x.dk"} for i in range(3)], "count": 3}
    )
    batch = _mock_response(status=204)
    with mock.patch("src.newsletter.sender.requests.get", return_value=page), mock.patch(
        "src.newsletter.sender.requests.post", return_value=batch
    ) as post:
        n = sender.sync_region_lists("Jylland")

    assert n == 3
    assert post.call_args.args[0].endswith("/v3/contacts/batch")
    body = post.call_args.kwargs["json"]["contacts"]
    assert {"email": "u0@x.dk", "listIds": [nconfig.BREVO_REGION_LISTS["Jylland"]]} in body


def test_sync_region_lists_dry_run_skips_network(set_creds):
    page = _mock_response(payload={"contacts": [{"email": "a@x.dk"}], "count": 1})
    with mock.patch("src.newsletter.sender.requests.get", return_value=page), mock.patch(
        "src.newsletter.sender.requests.post"
    ) as post:
        n = sender.sync_region_lists("Jylland", dry_run=True)
    assert n == 1
    assert post.call_count == 0


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


def test_fetch_unassigned_contacts_routes_region_less_contacts(set_creds):
    """E-mail-only signups (empty REGION) must land on the country-wide briefing."""
    page = _mock_response(
        payload={
            "contacts": [
                {"email": "noattr@x.dk"},
                {"email": "empty@x.dk", "attributes": {"REGION": ""}},
                {"email": "jylland@x.dk", "attributes": {"REGION": "Jylland"}},
                {"email": "nordpolen@x.dk", "attributes": {"REGION": "Nordpolen"}},
            ],
            "count": 4,
        }
    )
    with mock.patch("src.newsletter.sender.requests.get", return_value=page) as get:
        emails = sender.fetch_unassigned_contacts()

    assert emails == ["noattr@x.dk", "empty@x.dk", "nordpolen@x.dk"]
    # Not a filter query: whether Brevo matches an empty attribute is unspecified.
    assert "filter" not in get.call_args.kwargs["params"]


def test_fetch_unassigned_contacts_requires_key(monkeypatch):
    monkeypatch.setattr(nconfig, "BREVO_API_KEY", "")
    with pytest.raises(RuntimeError, match="BREVO_API_KEY"):
        sender.fetch_unassigned_contacts()


def test_sync_country_wide_list_uses_the_fallback_audience(set_creds):
    page = _mock_response(
        payload={"contacts": [{"email": "new@x.dk", "attributes": {}}], "count": 1}
    )
    batch = _mock_response(status=204)
    with mock.patch("src.newsletter.sender.requests.get", return_value=page), mock.patch(
        "src.newsletter.sender.requests.post", return_value=batch
    ) as post:
        n = sender.sync_region_lists("Hele landet")

    assert n == 1
    assert post.call_args.kwargs["json"]["contacts"] == [
        {"email": "new@x.dk", "listIds": [nconfig.BREVO_REGION_LISTS["Hele landet"]]}
    ]
