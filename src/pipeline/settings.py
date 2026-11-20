"""Environment-backed pipeline configuration.

Values are read on each call rather than frozen at import time so a process
started with a different ``--env-file`` (and tests that patch the environment)
always see the current configuration. No regulator URL or secret belongs here.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}

_PIPELINE_ROOT = Path(__file__).resolve().parent
_SRC_ROOT = _PIPELINE_ROOT.parent
_DEFAULT_DATA_DIR = _SRC_ROOT / "data"
_DEFAULT_SOURCES_FILE = _PIPELINE_ROOT / "sources.example.json"


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY


def _number(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s is not a number; using %s", name, default)
        return default


def _whole(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s is not an integer; using %s", name, default)
        return default


def _path(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    return Path(raw) if raw else default


def data_dir() -> Path:
    """Working directory for raw captures and the pipeline database."""
    return _path("PIPELINE_DATA_DIR", _DEFAULT_DATA_DIR)


def raw_dir() -> Path:
    """Where original API and page responses are written."""
    return _path("PIPELINE_RAW_DIR", data_dir() / "raw")


def database_path() -> Path:
    """SQLite file holding approved recalls and the review queue."""
    return _path("PIPELINE_DB", data_dir() / "recalls.db")


def sources_file() -> Path:
    """JSON registry of collectors. Copy sources.example.json and point here."""
    return _path("PIPELINE_SOURCES_FILE", _DEFAULT_SOURCES_FILE)


def approved_table() -> str:
    return os.getenv("PIPELINE_APPROVED_TABLE", "recalls").strip() or "recalls"


def review_table() -> str:
    return os.getenv("PIPELINE_REVIEW_TABLE", "review_queue").strip() or "review_queue"


def user_agent() -> str:
    return os.getenv(
        "PIPELINE_USER_AGENT",
        "Mozilla/5.0 (compatible; EDM-Dashboard/1.0; +https://everydosematters.org)",
    )


def http_timeout() -> float:
    return _number("PIPELINE_HTTP_TIMEOUT", 30.0)


def extract_timeout() -> float:
    return _number("PIPELINE_EXTRACT_TIMEOUT", 60.0)


def extract_max_chars() -> int:
    return _whole("PIPELINE_EXTRACT_MAX_CHARS", 12000)


def extract_max_tokens() -> int:
    return _whole("PIPELINE_EXTRACT_MAX_TOKENS", 1024)


def require_product_name() -> bool:
    return _flag("PIPELINE_REQUIRE_PRODUCT_NAME", "true")


def require_reason() -> bool:
    return _flag("PIPELINE_REQUIRE_REASON", "true")


def require_publish_date() -> bool:
    return _flag("PIPELINE_REQUIRE_PUBLISH_DATE", "true")


def date_pattern() -> str:
    """Regex used to accept publish_date values."""
    return os.getenv("PIPELINE_DATE_PATTERN", r"^\d{4}-\d{2}-\d{2}$")


def start_date() -> str:
    """Inclusive scrape window start (YYYY-MM-DD) for existing scrapers."""
    return os.getenv("PIPELINE_START_DATE", "2020-01-01")


def use_prefect() -> bool:
    """Whether to wrap the run in a Prefect flow when Prefect is installed.

    Off by default for local CLI runs. Prefetch's ephemeral server is optional
    orchestration, not required for collection.
    """
    return _flag("PIPELINE_USE_PREFECT", "false")


def auto_approve_valid() -> bool:
    """Write passing records straight to the approved table."""
    return _flag("PIPELINE_AUTO_APPROVE_VALID", "true")


def load_sources() -> list[dict]:
    """Load the collector registry from ``PIPELINE_SOURCES_FILE``."""
    path = sources_file()
    if not path.is_file():
        raise FileNotFoundError(
            f"PIPELINE_SOURCES_FILE not found: {path}. "
            "Copy src/pipeline/sources.example.json and set PIPELINE_SOURCES_FILE."
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("PIPELINE_SOURCES_FILE must contain a JSON array")
    return [item for item in payload if item.get("enabled", True)]
