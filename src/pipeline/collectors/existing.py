"""Run the site-specific scrapers already in ``src.scrapers``."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from src.models import DrugAlert
from src.pipeline import settings

# Legacy scrapers import ``scrapers.config`` (not ``src.scrapers.config``),
# which is how ``make scraper`` runs with PYTHONPATH=.:src.
_SRC_ROOT = Path(__file__).resolve().parents[2]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

_SCRAPER_IMPORTS = {
    "fdausa": ("src.scrapers.fdausa", "FDAUSAScraper"),
    "fdaghana": ("src.scrapers.fdaghana", "FDAGhanaScraper"),
    "healthcanada": ("src.scrapers.healthcanada", "HealthCanadaScraper"),
    "nafdac": ("src.scrapers.nafdac", "NafDacScraper"),
}


def run_existing_scraper(scraper_key: str) -> list[DrugAlert]:
    """Instantiate a known scraper and return standardised DrugAlert rows."""
    key = (scraper_key or "").strip().lower()
    if key not in _SCRAPER_IMPORTS:
        raise ValueError(
            f"Unknown scraper {scraper_key!r}. "
            f"Expected one of: {', '.join(sorted(_SCRAPER_IMPORTS))}"
        )

    module_name, class_name = _SCRAPER_IMPORTS[key]
    module = __import__(module_name, fromlist=[class_name])
    scraper_cls = getattr(module, class_name)
    start = datetime.strptime(settings.start_date(), "%Y-%m-%d")
    return scraper_cls(start).standardize(upload_to_db=False)
