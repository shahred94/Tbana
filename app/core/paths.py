"""Runtime paths shared by development and packaged desktop builds."""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RESOURCE_ROOT = Path(
    os.getenv("LIVETRIGGER_RESOURCE_DIR", PROJECT_ROOT)
).resolve()

DATA_ROOT = Path(
    os.getenv("LIVETRIGGER_DATA_DIR", PROJECT_ROOT)
).resolve()


def resource_path(*parts: str) -> Path:
    """Return a read-only application resource path."""

    return RESOURCE_ROOT.joinpath(*parts)


def data_path(*parts: str) -> Path:
    """Return a writable user-data path."""

    return DATA_ROOT.joinpath(*parts)
