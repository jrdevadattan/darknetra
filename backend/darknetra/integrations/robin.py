"""Offline index parser adapted from Robin search.py (MIT).

Copyright (c) 2025 Apurv Singh Gautam.
Source commit: 575d105e2f0fd61a450d5b4368535d0e83060354.
The anchor filtering and ordered trailing-slash deduplication are extracted from
fetch_search_results/get_search_results. See third_party/robin for the license
and changes. This module has no network or model capabilities.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

from selectolax.parser import HTMLParser

UPSTREAM_COMMIT = "575d105e2f0fd61a450d5b4368535d0e83060354"
MAX_HTML_BYTES = 1_000_000
MAX_ANCHORS = 2000


class IndexFormatError(ValueError):
    """Captured provider response is not a recognizable search result page."""


@dataclass(frozen=True)
class IndexHit:
    title: str
    url: str


def _index_target(href: str) -> str | None:
    """Validate an inert index locator; this does not prove Tor reachability."""
    if len(href) > 4096:
        return None
    try:
        # Ahmia may wrap a target in a local search redirect. Never accept an
        # arbitrary URL simply because its query contains an onion string.
        parsed = urlsplit(href)
        if parsed.path.rstrip("/") == "/search/redirect" and (
            (not parsed.scheme and not parsed.netloc)
            or (parsed.scheme == "https" and parsed.netloc == "ahmia.fi")
        ):
            values = parse_qs(parsed.query, max_num_fields=10).get("redirect_url", [])
            if len(values) != 1:
                return None
            href = values[0]
        if any(ord(char) < 33 or ord(char) == 127 for char in unquote(href)) or "\\" in href:
            return None
        parsed = urlsplit(href)
        host = parsed.hostname or ""
        if (
            parsed.scheme not in {"http", "https"}
            or not re.fullmatch(r"[a-z2-7]{56}\.onion", host)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or "search" in parsed.path.casefold()
        ):
            return None
        return urlunsplit((parsed.scheme, host, parsed.path, parsed.query, ""))
    except ValueError:
        return None


def parse_index(html: bytes, *, limit: int = 5) -> list[IndexHit]:
    """Read bounded saved HTML and return ordered index entries, never fetches.

    Locator checks establish HTTP(S) and a v3-shaped hostname only. They do not
    verify the onion key/checksum, that a service exists, or what it contains.
    """
    if len(html) > MAX_HTML_BYTES:
        raise ValueError("Index HTML exceeds parser byte limit")
    if not 1 <= limit <= 10:
        raise ValueError("Index result limit must be between 1 and 10")
    soup = HTMLParser(html)
    # Provider structure verified against Ahmia's tor_results.html template:
    # https://github.com/ahmia/ahmia-site/blob/master/ahmia/templates/tor_results.html
    page = soup.css_first("#ahmiaResultsPage")
    if page is None or soup.css_first("#challenge-form,.g-recaptcha,.h-captcha") is not None:
        raise IndexFormatError("Captured index is a challenge or unrecognized provider page")
    no_results = page.css_first("#noResults")
    results = page.css_first("ol.searchResults")
    if no_results is not None and results is None:
        return []
    if no_results is not None or results is None:
        raise IndexFormatError("Captured index has an inconsistent or unsupported layout")
    links: list[IndexHit] = []
    # Adapted from Robin fetch_search_results: traverse anchors, require a
    # meaningful title, and filter search/self links. selectolax replaces bs4.
    for anchor in results.css("li.result h4 a")[:MAX_ANCHORS]:
        title = " ".join(anchor.text(strip=True).split())[:300]
        link = _index_target(anchor.attributes.get("href") or "")
        if link is not None and len(title) > 3:
            links.append(IndexHit(title=title, url=link))

    # Adapted from Robin get_search_results; preserve first-seen order.
    seen_links: set[str] = set()
    unique_results: list[IndexHit] = []
    for res in links:
        clean_link = res.url.rstrip("/")
        if clean_link not in seen_links:
            seen_links.add(clean_link)
            unique_results.append(res)
            if len(unique_results) == limit:
                break
    if not unique_results:
        raise IndexFormatError("Captured index did not contain recognizable result entries")
    return unique_results
