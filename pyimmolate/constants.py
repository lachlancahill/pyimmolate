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

# All `None` defaults below mean "don't pass the flag — use Immolate's own default".
# Immolate's own defaults: -s empty (start of seed space), -n full seed pool
# (2,318,107,019,761), -c 1, -g 16, -p 0, -d 0. Override per-call via kwargs to run().
DEFAULT_START_SEED: str | None = None
DEFAULT_NUM_SEEDS: int | None = None
DEFAULT_CUTOFF: int | None = None
DEFAULT_THREAD_GROUPS: int | None = None
DEFAULT_PLATFORM: int | None = None
DEFAULT_DEVICE: int | None = None

GENERATED_FILTER_PREFIX = "pyimmolate_"
