"""RSS feed polling and press release page scraping."""

import logging
import re

import feedparser
import requests
from bs4 import BeautifulSoup

from .config import RSS_FEED_URL

logger = logging.getLogger(__name__)


def _extract_district_from_title(page_title: str) -> str:
    """Extract district name from page <title>, e.g.
    '... | Sydsjællands og Lolland-Falsters Politi' → 'Sydsjællands og Lolland-Falsters Politi'.
    """
    parts = page_title.rsplit(" | ", 1)
    if len(parts) == 2:
        return parts[1].strip()
    return ""


def _extract_thread_items(soup: BeautifulSoup) -> list[dict]:
    """Extract all thread items (timestamped updates) from the press release page.

    Each <div class="thread-item"> contains:
      - <p class="sc-gEvEer tGNaa">  → timestamp and district
      - <div class="sc-aXZVg jdSwMh"> → message body (one or more <p> tags)

    Returns items latest-first (as presented on the page).
    """
    thread = soup.find("div", class_="short-message-thread")
    if not thread:
        logger.warning("Could not find short-message-thread on page")
        return []

    thread_items = thread.find_all("div", class_="thread-item")
    if not thread_items:
        logger.warning("No thread-item divs found in short-message-thread")
        return []

    ts_pattern = re.compile(
        r"^(\d{1,2}\.\d{1,2}\.\d{4}\s+\d{2}:\d{2}:\d{2}\s+CEST)\s*\|"
    )

    items = []
    for ti in thread_items:
        meta_p = ti.find("p", class_=re.compile(r"sc-gEvEer"))
        timestamp = ""
        item_district = ""
        if meta_p:
            meta_text = meta_p.get_text(" ", strip=True)
            match = ts_pattern.match(meta_text)
            if match:
                timestamp = match.group(1)
                bar_idx = meta_text.find("|")
                if bar_idx != -1:
                    item_district = meta_text[bar_idx + 1:].strip()

        body = ""
        content_div = ti.find("div", class_=re.compile(r"sc-aXZVg"))
        if content_div:
            paragraphs = content_div.find_all("p")
            if paragraphs:
                body = "\n\n".join(
                    p.get_text(" ", strip=True) for p in paragraphs
                )
                body = body.replace("\xa0", " ")

        items.append({
            "body": body,
            "timestamp": timestamp,
            "district": item_district,
        })

    return items


def fetch_feed() -> list[dict]:
    """Fetch and parse the RSS feed. Returns raw items with guid/title/link/pub_date."""
    logger.debug("Fetching RSS feed: %s", RSS_FEED_URL)
    feed = feedparser.parse(RSS_FEED_URL)

    if feed.bozo and not feed.entries:
        logger.error("Failed to parse RSS feed: %s", feed.bozo_exception)
        return []

    items = []
    for entry in feed.entries:
        items.append({
            "guid": entry.get("guid") or entry.get("link", ""),
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "pub_date": entry.get("published", ""),
        })

    logger.debug("Fetched %d items from RSS", len(items))
    return items


def fetch_press_release(link: str) -> tuple[str, list[dict]]:
    """Fetch a press release page and extract (district, thread_items).

    Returns:
        (district, thread_items) — thread_items is a list of dicts,
        each with 'body', 'timestamp', 'district'. Latest first.
        Empty list on failure.
    """
    logger.debug("Fetching press release: %s", link)
    try:
        resp = requests.get(link, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error("Failed to fetch press release %s: %s", link, e)
        return "", []

    soup = BeautifulSoup(resp.text, "html.parser")

    district = ""
    title_tag = soup.find("title")
    if title_tag:
        district = _extract_district_from_title(title_tag.get_text(strip=True))

    thread_items = _extract_thread_items(soup)

    if not district and thread_items:
        district = thread_items[0].get("district", "")

    return district, thread_items
