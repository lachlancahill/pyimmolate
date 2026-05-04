"""Fetches and caches the Immolate Windows binary from GitHub releases."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import requests

from pyimmolate.constants import (
    BINARY_NAME,
    IMMOLATE_DOWNLOAD_URL,
    IMMOLATE_VERSION,
    INSTALL_DIR,
)


def ensure_immolate() -> Path:
    """Ensure Immolate is downloaded and extracted; return the install directory.

    The install directory contains `immolate.exe` (or equivalent), `filters/`,
    and `lib/`. Re-uses the cached install if already present.
    """
    if _binary_path(INSTALL_DIR).exists():
        return INSTALL_DIR

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    _download_and_extract(IMMOLATE_DOWNLOAD_URL, INSTALL_DIR)

    binary = _binary_path(INSTALL_DIR)
    if not binary.exists():
        raise RuntimeError(
            f"Immolate {IMMOLATE_VERSION} extracted to {INSTALL_DIR} but expected "
            f"binary {BINARY_NAME!r} was not found. Archive contents: "
            f"{[p.name for p in INSTALL_DIR.iterdir()]}"
        )
    return INSTALL_DIR


def _download_and_extract(url: str, dest: Path) -> None:
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()
    archive = io.BytesIO(response.content)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)


def _binary_path(install_dir: Path) -> Path:
    """Path the binary is expected at. Some archives nest contents under a folder;
    if BINARY_NAME isn't directly under install_dir but exists in a single
    subfolder, treat that subfolder as the install dir."""
    direct = install_dir / BINARY_NAME
    if direct.exists():
        return direct
    if install_dir.exists():
        for child in install_dir.iterdir():
            if child.is_dir():
                nested = child / BINARY_NAME
                if nested.exists():
                    return nested
    return direct


def install_path() -> Path:
    """Return the directory containing immolate.exe (downloads if needed)."""
    ensure_immolate()
    binary = _binary_path(INSTALL_DIR)
    return binary.parent
