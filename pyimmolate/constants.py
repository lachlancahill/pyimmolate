"""Hardcoded parameters for pyimmolate. No CLI args; edit here to change defaults."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_cache_path

IMMOLATE_VERSION = "v1.0.1f.1"
IMMOLATE_REPO = "SpectralPack/Immolate"
IMMOLATE_ASSET = "Immolate.zip"
IMMOLATE_DOWNLOAD_URL = (
    f"https://github.com/{IMMOLATE_REPO}/releases/download/"
    f"{IMMOLATE_VERSION}/{IMMOLATE_ASSET}"
)

IMMOLATE_RAW_BASE = (
    f"https://raw.githubusercontent.com/{IMMOLATE_REPO}/{IMMOLATE_VERSION}"
)

CACHE_ROOT: Path = user_cache_path("pyimmolate", "pyimmolate")
INSTALL_DIR: Path = CACHE_ROOT / IMMOLATE_VERSION
BINARY_NAME = "immolate.exe"

DEFAULT_START_SEED = "11111111"
DEFAULT_NUM_SEEDS = 1_000_000
DEFAULT_CUTOFF = 1
DEFAULT_THREAD_GROUPS = 16
DEFAULT_PLATFORM: int | None = None
DEFAULT_DEVICE: int | None = None

GENERATED_FILTER_PREFIX = "pyimmolate_"
