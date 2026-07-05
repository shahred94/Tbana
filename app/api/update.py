"""Desktop application update checks backed by GitHub Releases."""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter

from app.core.config import settings


router = APIRouter(
    prefix="/api/update",
    tags=["Update"],
)

_VERSION_PATTERN = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$",
    re.IGNORECASE,
)


class UpdateLookupError(RuntimeError):
    """A safe, user-facing update lookup failure."""


def parse_version(value: str) -> tuple[int, int, int]:
    """Parse a release tag such as v1.2.3 into a comparable tuple."""

    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError("Version must use the major.minor.patch format.")
    return tuple(int(part) for part in match.groups())


def _latest_release() -> dict:
    repository = settings.update_repository.strip()
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        raise UpdateLookupError("The update repository is not configured.")

    request = Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": (
                f"TBana-Stream-Updater/{settings.app_version}"
            ),
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )

    try:
        with urlopen(request, timeout=6) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 404:
            raise UpdateLookupError(
                "No published release is available yet."
            ) from error
        raise UpdateLookupError(
            "GitHub could not complete the update check."
        ) from error
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
        raise UpdateLookupError(
            "Unable to connect to the update server."
        ) from error


def _installer_asset(release: dict) -> dict | None:
    executable_assets = [
        asset
        for asset in release.get("assets", [])
        if str(asset.get("name", "")).lower().endswith(".exe")
    ]
    if not executable_assets:
        return None

    return next(
        (
            asset
            for asset in executable_assets
            if "setup" in str(asset.get("name", "")).lower()
        ),
        executable_assets[0],
    )


@router.get("/check")
def check_for_update() -> dict:
    current_version = settings.app_version

    try:
        release = _latest_release()
        latest_version = str(release.get("tag_name", "")).lstrip("vV")
        update_available = (
            parse_version(latest_version)
            > parse_version(current_version)
        )
    except (UpdateLookupError, ValueError) as error:
        return {
            "status": "unavailable",
            "current_version": current_version,
            "message": str(error),
        }

    installer = _installer_asset(release)
    release_url = str(release.get("html_url", ""))
    download_url = (
        str(installer.get("browser_download_url", ""))
        if installer
        else release_url
    )

    return {
        "status": "ok",
        "current_version": current_version,
        "latest_version": latest_version,
        "update_available": update_available,
        "release_name": str(release.get("name") or latest_version),
        "release_notes": str(release.get("body") or ""),
        "published_at": release.get("published_at"),
        "download_url": download_url if update_available else "",
        "direct_download": bool(installer),
        "release_url": release_url,
    }
