"""Tests for fetcher.py — RSS parsing and press release scraping."""

import time
from datetime import datetime, timezone
from unittest import mock

import requests
from bs4 import BeautifulSoup

from src.bot import fetcher


class TestExtractDistrictFromTitle:
    def test_extracts_district_from_title(self):
        result = fetcher._extract_district_from_title(
            "Test Update | Sydsjællands og Lolland-Falsters Politi"
        )
        assert result == "Sydsjællands og Lolland-Falsters Politi"

    def test_extracts_from_title_with_single_part(self):
        result = fetcher._extract_district_from_title("Test Update | Politi")
        assert result == "Politi"

    def test_returns_empty_when_no_separator(self):
        result = fetcher._extract_district_from_title("Just a title")
        assert result == ""

    def test_returns_empty_for_empty_title(self):
        result = fetcher._extract_district_from_title("")
        assert result == ""


class TestExtractThreadItems:
    def test_extracts_multiple_thread_items(self, sample_html_with_thread):
        soup = BeautifulSoup(sample_html_with_thread, "html.parser")
        items = fetcher._extract_thread_items(soup)

        assert len(items) == 2
        assert items[0]["body"] == "Seneste opdatering: personen er fundet."
        assert items[0]["timestamp"] == "3.8.2026 23:50:26 CEST"
        assert items[0]["district"] == "Sydsjællands og Lolland-Falsters Politi"
        assert items[0]["sm_id"] == "sm-12346"
        assert items[1]["sm_id"] == "sm-12345"

    def test_second_item_has_merged_paragraphs(self, sample_html_with_thread):
        soup = BeautifulSoup(sample_html_with_thread, "html.parser")
        items = fetcher._extract_thread_items(soup)

        assert "Vi leder efter en 78-årig mand." in items[1]["body"]
        assert "Kontakt politiet på 114." in items[1]["body"]
        assert "\n\n" in items[1]["body"]

    def test_returns_empty_list_when_no_thread_div(self, sample_html_no_thread):
        soup = BeautifulSoup(sample_html_no_thread, "html.parser")
        items = fetcher._extract_thread_items(soup)
        assert items == []

    def test_returns_empty_list_when_no_thread_items(self):
        html = """
        <html><body>
          <div class="short-message-thread"></div>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = fetcher._extract_thread_items(soup)
        assert items == []

    def test_handles_missing_timestamp_paragraph(self):
        html = """
        <html><body>
          <div class="short-message-thread">
            <div class="thread-item">
              <div class="sc-aXZVg jdSwMh">
                <div><p>Body without timestamp paragraph.</p></div>
              </div>
            </div>
          </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = fetcher._extract_thread_items(soup)
        assert len(items) == 1
        assert items[0]["body"] == "Body without timestamp paragraph."
        assert items[0]["timestamp"] == ""
        assert items[0]["sm_id"] == ""

    def test_handles_missing_body_div(self):
        html = """
        <html><body>
          <div class="short-message-thread">
            <div class="thread-item">
              <p class="sc-gEvEer tGNaa">3.8.2026 14:00:00 CEST | Politi</p>
            </div>
          </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = fetcher._extract_thread_items(soup)
        assert len(items) == 1
        assert items[0]["body"] == ""
        assert items[0]["timestamp"] == "3.8.2026 14:00:00 CEST"

    def test_handles_timestamp_with_extra_whitespace(self):
        html = """
        <html><body>
          <div class="short-message-thread">
            <div class="thread-item">
              <p class="sc-gEvEer tGNaa">  3.8.2026 14:00:00 CEST  |  Politi  </p>
              <div class="sc-aXZVg jdSwMh">
                <div><p>Message.</p></div>
              </div>
            </div>
          </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items = fetcher._extract_thread_items(soup)
        assert items[0]["timestamp"] == "3.8.2026 14:00:00 CEST"
        assert items[0]["district"] == "Politi"


class TestFetchFeed:
    @mock.patch("src.bot.fetcher.requests.get")
    @mock.patch("src.bot.fetcher.feedparser")
    def test_parses_rss_entries(self, mock_feedparser, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"<rss></rss>"
        mock_feedparser.parse.return_value.bozo = False
        mock_feedparser.parse.return_value.entries = [
            {
                "guid": "guid-1",
                "title": "Title 1",
                "link": "http://example.com/1",
                "published": "Mon, 03 Aug 2026",
            },
            {
                "guid": "guid-2",
                "title": "Title 2",
                "link": "http://example.com/2",
                "published": "Mon, 03 Aug 2026",
            },
        ]

        items = fetcher.fetch_feed()

        assert len(items) == 2
        assert items[0]["guid"] == "guid-1"
        assert items[0]["title"] == "Title 1"
        assert items[1]["guid"] == "guid-2"
        assert "pub_dt" in items[0]

    @mock.patch("src.bot.fetcher.requests.get")
    @mock.patch("src.bot.fetcher.feedparser")
    def test_parses_pub_dt_from_published_parsed(self, mock_feedparser, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"<rss></rss>"
        mock_feedparser.parse.return_value.bozo = False
        # feedparser returns time.struct_time as a 9-tuple in UTC
        pub_struct = time.gmtime(1754222400)  # 2025-08-03 12:00:00 UTC
        mock_feedparser.parse.return_value.entries = [
            {
                "guid": "g",
                "title": "t",
                "link": "l",
                "published": "Sun, 03 Aug 2025 12:00:00 +0000",
                "published_parsed": pub_struct,
            }
        ]

        items = fetcher.fetch_feed()
        assert items[0]["pub_dt"] == datetime(2025, 8, 3, 12, 0, 0, tzinfo=timezone.utc)

    @mock.patch("src.bot.fetcher.requests.get")
    @mock.patch("src.bot.fetcher.feedparser")
    def test_falls_back_guid_to_link(self, mock_feedparser, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"<rss></rss>"
        mock_feedparser.parse.return_value.bozo = False
        mock_feedparser.parse.return_value.entries = [
            {
                "title": "No GUID",
                "link": "http://example.com/no-guid",
                "published": "",
            }
        ]

        items = fetcher.fetch_feed()
        assert items[0]["guid"] == "http://example.com/no-guid"

    @mock.patch("src.bot.fetcher.requests.get")
    @mock.patch("src.bot.fetcher.feedparser")
    def test_returns_empty_on_bozo_with_no_entries(self, mock_feedparser, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"<rss></rss>"
        mock_feedparser.parse.return_value.bozo = True
        mock_feedparser.parse.return_value.entries = []

        items = fetcher.fetch_feed()
        assert items == []

    @mock.patch("src.bot.fetcher.requests.get")
    @mock.patch("src.bot.fetcher.feedparser")
    def test_returns_entries_despite_bozo(self, mock_feedparser, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"<rss></rss>"
        mock_feedparser.parse.return_value.bozo = True
        mock_feedparser.parse.return_value.entries = [
            {"guid": "g", "title": "t", "link": "l", "published": "p"}
        ]

        items = fetcher.fetch_feed()
        assert len(items) == 1

    @mock.patch("src.bot.fetcher.requests.get")
    @mock.patch("src.bot.fetcher.feedparser")
    def test_handles_empty_pub_date(self, mock_feedparser, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"<rss></rss>"
        mock_feedparser.parse.return_value.bozo = False
        mock_feedparser.parse.return_value.entries = [
            {"guid": "g", "title": "t", "link": "l"}
        ]

        items = fetcher.fetch_feed()
        assert items[0]["pub_date"] == ""
        assert items[0]["pub_dt"] is None

    @mock.patch("src.bot.fetcher.requests.get")
    def test_returns_empty_on_network_error(self, mock_get):
        import requests as r
        mock_get.side_effect = r.ConnectionError("DNS failure")

        items = fetcher.fetch_feed()
        assert items == []


class TestFetchPressRelease:
    @mock.patch("src.bot.fetcher.requests.get")
    def test_returns_district_and_thread_items(
        self, mock_get, sample_html_with_thread
    ):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = sample_html_with_thread
        mock_get.return_value.raise_for_status.return_value = None

        district, items = fetcher.fetch_press_release("http://example.com")

        assert district == "Sydsjællands og Lolland-Falsters Politi"
        assert len(items) == 2
        assert items[0]["body"] == "Seneste opdatering: personen er fundet."

    @mock.patch("src.bot.fetcher.requests.get")
    def test_handles_http_error(self, mock_get):
        mock_get.side_effect = requests.RequestException("Connection error")

        district, items = fetcher.fetch_press_release("http://example.com")

        assert district == ""
        assert items == []

    @mock.patch("src.bot.fetcher.requests.get")
    def test_falls_back_district_from_thread_item(self, mock_get):
        html = """
        <html>
        <head><title>No District Here</title></head>
        <body>
          <div class="short-message-thread">
            <div class="thread-item">
              <p class="sc-gEvEer tGNaa">3.8.2026 14:00:00 CEST | Nordjyllands Politi</p>
              <div class="sc-aXZVg jdSwMh">
                <div><p>Body.</p></div>
              </div>
            </div>
          </div>
        </body>
        </html>
        """
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = html
        mock_get.return_value.raise_for_status.return_value = None

        district, items = fetcher.fetch_press_release("http://example.com")

        assert district == "Nordjyllands Politi"

    @mock.patch("src.bot.fetcher.requests.get")
    def test_handles_no_title_tag(self, mock_get):
        html = """
        <html><head></head>
        <body>
          <div class="short-message-thread">
            <div class="thread-item">
              <p class="sc-gEvEer tGNaa">3.8.2026 14:00:00 CEST | Politi</p>
              <div class="sc-aXZVg jdSwMh"><div><p>B.</p></div></div>
            </div>
          </div>
        </body></html>
        """
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = html
        mock_get.return_value.raise_for_status.return_value = None

        district, items = fetcher.fetch_press_release("http://example.com")
        assert district == "Politi"


class TestFetchFeedIntegration:
    """Light integration test — hits the live RSS feed."""

    def test_fetches_live_rss_without_error(self):
        items = fetcher.fetch_feed()

        assert isinstance(items, list)
        assert len(items) > 0
        for item in items:
            assert "guid" in item
            assert "title" in item
            assert "link" in item
            assert isinstance(item["guid"], str)
            assert len(item["guid"]) > 0
