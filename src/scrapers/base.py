"""Base scraper utilities shared across site-specific scrapers."""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, final

import requests
from bs4 import BeautifulSoup

from src.models import DrugAlert

from .utils import (
    NON_DRUG_LEADING_TOKENS,
    extract_drug_token,
    match_oncology_token,
    read_json,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class BaseScraper(ABC):
    """Abstract base class for all site-specific scrapers."""

    def __init__(
        self,
        url: Optional[str] = None,
        *,
        args: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
        start_date: Optional[datetime] = None,
        db_bath: Optional[str] = None,
        oncology_drugs_path: Optional[str] = None,
    ) -> None:
        """Initialize the scraper with a base URL and optional request args."""

        self.url = url
        self.args = args or {}
        self.timeout = timeout
        self.start_date = start_date
        self.search_url = "https://webapis.oncology.gov/drugdictionary/v1/Drugs/search"
        self.nci_url = "https://www.cancer.gov/about-cancer/treatment/drugs/cancer-drugs"

        # Safe default UA
        self.args.setdefault("headers", {})
        self.args["headers"].setdefault(
            "User-Agent",
            "Mozilla/5.0 (compatible; EDM-Dashboard/1.0; +https://everydosematters.org)",
        )
        self.oncology_drugs_path = oncology_drugs_path or str(DATA_DIR / "nci_oncology_drugs.json")
        self.oncology_drugs_catalog_path = str(
            Path(self.oncology_drugs_path).with_name("nci_oncology_drugs_catalog.json")
        )
        self.oncology_drugs = read_json(self.oncology_drugs_path)
        self.db_path = db_bath or str(DATA_DIR / "recalls.db")
        self.nci_origin = "https://www.cancer.gov"

    def scrape(self, url: Optional[str] = None) -> Dict[str, Any]:
        """Fetch a URL and return minimal response metadata plus parsed HTML."""

        target = url or self.url
        resp = requests.get(target, timeout=self.timeout, **self.args)
        resp.raise_for_status()

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        return {
            "final_url": resp.url,
            "status_code": resp.status_code,
            "html": soup,
        }

    def get_json(self, url: str, params: dict) -> Dict:
        """Fetch a json instead."""

        r = requests.get(url, params=params)
        data = r.json()
        return data

    def standardize(self, upload_to_db: bool = False) -> List[DrugAlert]:
        """Standardize the scraper's data into a list of DrugAlert objects."""

        raise NotImplementedError

    @final
    def make_record_id(self, source_id: str, drug_name: str, record_id: str) -> str:
        """Build a stable record identifier from heterogeneous parts."""

        raw = "||".join([source_id, drug_name, record_id])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @final
    def get_nci_name(self, drug_name: str, approved_drugs: list = None) -> Optional[str]:
        """Look up the NCI dictionary for a product name or phrase."""

        if approved_drugs is None:
            approved_drugs = []
        if not drug_name:
            return None
        if not approved_drugs:
            approved_drugs = self.oncology_drugs
        if not approved_drugs:
            approved_drugs = self.fetch_oncology_drug_names()

        return match_oncology_token(drug_name, approved_drugs)

    def _absolute_nci_url(self, href: str) -> str:
        href = (href or "").strip()
        if href.startswith("http://") or href.startswith("https://"):
            return href
        if href.startswith("/"):
            return f"{self.nci_origin}{href}"
        return f"{self.nci_origin}/about-cancer/treatment/drugs/{href}"

    def fetch_oncology_drug_names(self) -> list[str]:
        """Get the approved cancer drugs and their official NCI page links."""

        response = requests.get(self.nci_url, headers=self.args["headers"], timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        drug_names: list[str] = []
        catalog: list[dict[str, str]] = []
        seen_tokens: set[str] = set()
        seen_pages: set[str] = set()

        # The page lists drugs as links inside the main content area.
        # Keep the real href — brand names often resolve to a different slug.
        div = soup.select("div.usa-prose.usa-prose--ncids-full-html")
        uls = div[0].select("ul.usa-list.usa-list--unstyled")
        for ul in uls:
            for li in ul.select("li"):
                anchor = li.find("a", href=True)
                label = (anchor.get_text(" ", strip=True) if anchor else li.get_text(strip=True))
                token = extract_drug_token(label)
                if token and token not in NON_DRUG_LEADING_TOKENS and token not in seen_tokens:
                    seen_tokens.add(token)
                    drug_names.append(token)

                if not anchor:
                    continue
                info_url = self._absolute_nci_url(anchor["href"])
                page_id = info_url.rstrip("/").rsplit("/", 1)[-1].lower()
                if not page_id or page_id in seen_pages:
                    continue
                seen_pages.add(page_id)
                catalog.append(
                    {
                        "id": page_id,
                        "name": label,
                        "info_url": info_url,
                        "match_token": token or page_id,
                    }
                )

        self.oncology_drugs = drug_names
        with open(self.oncology_drugs_path, "w", encoding="utf-8") as handle:
            json.dump(drug_names, handle, indent=2)
        with open(self.oncology_drugs_catalog_path, "w", encoding="utf-8") as handle:
            json.dump(catalog, handle, indent=2)
        return drug_names
