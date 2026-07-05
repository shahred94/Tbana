"""TikTok gift catalogue API."""

from __future__ import annotations

import html
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, HTTPException


router = APIRouter(
    prefix="/api/gifts",
    tags=["Gift catalogue"],
)

CATALOG_BASE_URL = "https://streamtoearn.io/gifts"
DEFAULT_REGION = "MY"
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

REGION_PATTERN = re.compile(
    r'<a[^>]+href="[^"]*\?region=(?P<code>[A-Za-z]{2})'
    r'[^"]*"[^>]*>(?P<name>.*?)</a>',
    flags=re.IGNORECASE | re.DOTALL,
)

_cache_lock = threading.Lock()
_cached_catalogs: dict[str, dict] = {}


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


def parse_regions(page_html: str) -> list[dict]:
    """Extract selectable two-letter gift catalogue regions."""

    regions = {}

    for match in REGION_PATTERN.finditer(page_html):
        code = match.group("code").upper()
        name = _clean_text(match.group("name"))

        if name:
            regions[code] = name

    return [
        {
            "code": code,
            "name": name,
        }
        for code, name in sorted(
            regions.items(),
            key=lambda item: item[1].casefold(),
        )
    ]


def normalize_region(region: str | None) -> str:
    """Return a safe two-letter catalogue region."""

    normalized = str(
        region or DEFAULT_REGION
    ).strip().upper()

    if not re.fullmatch(
        r"[A-Z]{2}",
        normalized,
    ):
        raise HTTPException(
            status_code=400,
            detail="Region must be a two-letter country code.",
        )

    return normalized


def catalog_url(region: str) -> str:
    """Build the upstream catalogue URL without accepting URL fragments."""

    return (
        f"{CATALOG_BASE_URL}?"
        + urlencode(
            {
                "region": region,
            }
        )
    )


def _download_catalog(region: str) -> tuple[list[dict], list[dict]]:
    source_url = catalog_url(region)
    request = urllib.request.Request(
        source_url,
        headers={
            "User-Agent": "TBanaStream/1.0",
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

    page_html = payload.decode(
        "utf-8",
        errors="replace",
    )
    gifts = parse_gift_catalog(page_html)

    if not gifts:
        raise ValueError(
            "No gifts were found in the catalogue."
        )

    return gifts, parse_regions(page_html)


@router.get("/catalog")
def get_gift_catalog(region: str = DEFAULT_REGION):
    """Return gift icons for one selected country with a short cache."""

    selected_region = normalize_region(region)
    source_url = catalog_url(selected_region)
    now = time.monotonic()

    with _cache_lock:
        cached = _cached_catalogs.get(
            selected_region
        )

        if (
            cached
            and now < cached["expires_at"]
        ):
            return {
                "gifts": cached["gifts"],
                "regions": cached["regions"],
                "region": selected_region,
                "source": source_url,
                "cached": True,
            }

        try:
            gifts, regions = _download_catalog(
                selected_region
            )

        except (
            OSError,
            ValueError,
            urllib.error.URLError,
        ) as error:
            if cached:
                return {
                    "gifts": cached["gifts"],
                    "regions": cached["regions"],
                    "region": selected_region,
                    "source": source_url,
                    "cached": True,
                    "stale": True,
                }

            raise HTTPException(
                status_code=502,
                detail=(
                    "Gift catalogue is currently unavailable."
                ),
            ) from error

        _cached_catalogs[selected_region] = {
            "gifts": gifts,
            "regions": regions,
            "expires_at": now + CACHE_SECONDS,
        }

        return {
            "gifts": gifts,
            "regions": regions,
            "region": selected_region,
            "source": source_url,
            "cached": False,
        }
