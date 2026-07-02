"""TikTok gift catalogue API."""

from __future__ import annotations

import html
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api/gifts",
    tags=["Gift catalogue"],
)

CATALOG_URL = "https://streamtoearn.io/gifts?region=MY"
CACHE_SECONDS = 6 * 60 * 60
MAX_CATALOG_BYTES = 4 * 1024 * 1024
ALLOWED_IMAGE_HOSTS = {
    "p16-webcast.tiktokcdn.com",
}

GIFT_PATTERN = re.compile(
    r'<div\s+class="gift"[^>]*>'
    r'.*?<img[^>]+src="(?P<icon>https://[^"]+)"'
    r'[^>]+alt="[^"]*TikTok gift"[^>]*>'
    r'.*?<p\s+class="gift-name">(?P<name>.*?)</p>'
    r'.*?<p\s+class="gift-price">\s*(?P<coins>\d+)',
    flags=re.IGNORECASE | re.DOTALL,
)

_cache_lock = threading.Lock()
_cached_gifts: list[dict] = []
_cache_expires_at = 0.0


def _clean_text(value: str) -> str:
    """Remove markup and decode HTML entities."""

    without_tags = re.sub(
        r"<[^>]+>",
        "",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        html.unescape(without_tags),
    ).strip()


def parse_gift_catalog(page_html: str) -> list[dict]:
    """Extract gift names, coin values, and trusted TikTok image URLs."""

    gifts = []
    seen_names = set()

    for match in GIFT_PATTERN.finditer(page_html):
        name = _clean_text(
            match.group("name")
        )
        icon_url = html.unescape(
            match.group("icon")
        )
        parsed_url = urlparse(icon_url)
        normalized_name = name.casefold()

        if (
            not name
            or normalized_name in seen_names
            or parsed_url.scheme != "https"
            or parsed_url.hostname not in ALLOWED_IMAGE_HOSTS
        ):
            continue

        seen_names.add(normalized_name)
        gifts.append(
            {
                "name": name,
                "coins": int(
                    match.group("coins")
                ),
                "icon_url": icon_url,
            }
        )

    return gifts


def _download_catalog() -> list[dict]:
    request = urllib.request.Request(
        CATALOG_URL,
        headers={
            "User-Agent": "LiveTrigger/1.0",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=15,
    ) as response:
        payload = response.read(
            MAX_CATALOG_BYTES + 1
        )

    if len(payload) > MAX_CATALOG_BYTES:
        raise ValueError(
            "Gift catalogue response is too large."
        )

    gifts = parse_gift_catalog(
        payload.decode(
            "utf-8",
            errors="replace",
        )
    )

    if not gifts:
        raise ValueError(
            "No gifts were found in the catalogue."
        )

    return gifts


@router.get("/catalog")
def get_gift_catalog():
    """Return Malaysia gift icons with a short in-memory cache."""

    global _cached_gifts
    global _cache_expires_at

    now = time.monotonic()

    with _cache_lock:
        if (
            _cached_gifts
            and now < _cache_expires_at
        ):
            return {
                "gifts": _cached_gifts,
                "source": CATALOG_URL,
                "cached": True,
            }

        try:
            gifts = _download_catalog()

        except (
            OSError,
            ValueError,
            urllib.error.URLError,
        ) as error:
            if _cached_gifts:
                return {
                    "gifts": _cached_gifts,
                    "source": CATALOG_URL,
                    "cached": True,
                    "stale": True,
                }

            raise HTTPException(
                status_code=502,
                detail=(
                    "Gift catalogue is currently unavailable."
                ),
            ) from error

        _cached_gifts = gifts
        _cache_expires_at = (
            now + CACHE_SECONDS
        )

        return {
            "gifts": gifts,
            "source": CATALOG_URL,
            "cached": False,
        }
