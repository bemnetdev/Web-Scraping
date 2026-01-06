"""
Supreme Court Verdict Downloader
================================

Responsibilities:
- Query the official Supreme Court verdict search API
- Extract verdict metadata
- Download verdict PDF files
- Persist metadata for traceability and auditability
- Log all major steps for observability and debugging
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter, Retry

# ============================================================================
# Configuration
# ============================================================================

API_URL = "https://supremedecisions.court.gov.il/Home/SearchVerdicts"
DOWNLOAD_BASE_URL = "https://supremedecisions.court.gov.il/Home/Download"

OUTPUT_DIR = Path("output")
DOCUMENTS_DIR = OUTPUT_DIR / "documents"
METADATA_PATH = OUTPUT_DIR / "metadata.json"
LOG_PATH = OUTPUT_DIR / "download_log.txt"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)

# ============================================================================
# HTTP Configuration
# ============================================================================

HEADERS = {
    "User-Agent": "SupremeCourtDecisionScraper/1.0",
    "Accept": "*/*",
    "Referer": "https://supremedecisions.court.gov.il/Pages/fullsearch.aspx",
}

SEARCH_PAYLOAD = {
    "document": {
        "PublishFrom": "2025-09-30T21:00:00.000Z",
        "PublishTo": "2025-09-30T21:00:00.000Z",
        "Type": [{"parent": 0, "value": 2, "text": "פסק-דין"}],
        "Technical": 0,
        "dateType": 2,
        "CodeTypes": [2],
    },
    "AllSubjects": [{"Subject": None, "SubSubject": None, "SubSubSubject": None}],
    "Counsel": [],
    "Parties": [],
    "SearchText": [],
    "lan": "1",
}

# ============================================================================
# Core Downloader
# ============================================================================


class SupremeCourtDownloader:
    """
    End-to-end downloader for Supreme Court verdicts.

    This class encapsulates:
    - API communication
    - Download job creation
    - File downloads with retries
    - Metadata persistence
    """

    def __init__(self) -> None:
        self.session = self._create_session()
        self.metadata: List[Dict] = []

    # ------------------------------------------------------------------ #
    # Session Setup
    # ------------------------------------------------------------------ #

    @staticmethod
    def _create_session() -> requests.Session:
        """
        Create a resilient HTTP session with retries and backoff.

        Returns:
            Configured requests.Session instance.
        """
        session = requests.Session()

        retries = Retry(
            total=5,
            backoff_factor=1.0,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )

        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.headers.update(HEADERS)

        return session

    # ------------------------------------------------------------------ #
    # API Layer
    # ------------------------------------------------------------------ #

    def fetch_verdicts(self) -> List[Dict]:
        """
        Fetch verdict metadata from the Supreme Court search API.

        Returns:
            List of verdict dictionaries returned by the API.
        """
        logger.info("Requesting verdict list from Supreme Court API")

        try:
            response = self.session.post(
                API_URL,
                json=SEARCH_PAYLOAD,
                timeout=20,
            )
            response.raise_for_status()

            verdicts = response.json().get("data", [])
            logger.info("Fetched %d verdict records", len(verdicts))
            return verdicts

        except Exception as exc:
            logger.exception("Failed to fetch verdicts: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # Download Job Construction
    # ------------------------------------------------------------------ #

    def create_download_jobs(self, cases: List[Dict]) -> List[Dict]:
        """
        Convert API verdict records into concrete download jobs.

        Args:
            cases: Raw verdict metadata records.

        Returns:
            List of download job dictionaries.
        """
        jobs: List[Dict] = []

        for case in cases:
            path = case.get("PathForWeb")
            file_name = case.get("FileName")

            if not path or not file_name:
                continue

            url = (
                f"{DOWNLOAD_BASE_URL}"
                f"?path={path}&fileName={file_name}&type=2"
            )

            jobs.append({"url": url, "case": case})

        logger.info("Prepared %d download jobs", len(jobs))
        return jobs

    # ------------------------------------------------------------------ #
    # Utility Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_dotnet_date(value: Optional[str]) -> Optional[str]:
        """
        Convert a .NET serialized date string into ISO format.

        Args:
            value: String in '/Date(1696118400000)/' format.

        Returns:
            ISO date string (YYYY-MM-DD) or None.
        """
        if not value:
            return None

        try:
            timestamp_ms = int(value.strip("/Date()"))
            return datetime.utcfromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d")
        except Exception:
            return None

    @staticmethod
    def infer_extension(filename: str) -> str:
        """
        Infer file extension from filename.

        Defaults to 'pdf' when missing or malformed.

        Args:
            filename: Original filename.

        Returns:
            Lowercase file extension.
        """
        if "." in filename:
            return filename.rsplit(".", 1)[-1].lower()
        return "pdf"

    # ------------------------------------------------------------------ #
    # Download Logic
    # ------------------------------------------------------------------ #

    def download_file(self, job: Dict, index: int, total: int) -> None:
        """
        Download a single verdict file with retry logic.

        Args:
            job: Download job dictionary.
            index: Current file index.
            total: Total number of files.
        """
        case = job["case"]
        url = job["url"]

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        original_name = case.get("DocName") or qs["fileName"][0]
        extension = self.infer_extension(original_name)

        local_filename = f"case_{index:03d}.{extension}"
        local_path = DOCUMENTS_DIR / local_filename

        for attempt in range(1, 6):
            try:
                logger.info(
                    "Downloading %d/%d (attempt %d): %s",
                    index,
                    total,
                    attempt,
                    local_filename,
                )

                with self.session.get(url, stream=True, timeout=60) as response:
                    response.raise_for_status()

                    with open(local_path, "wb") as fh:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                fh.write(chunk)

                file_size = local_path.stat().st_size

                self.metadata.append(
                    {
                        "index": index,
                        "case_id": case.get("CaseId"),
                        "case_number": case.get("CaseNum"),
                        "parties": case.get("CaseName"),
                        "case_description": case.get("CaseDesc"),
                        "decision_type": case.get("Type"),
                        "decision_date": self.parse_dotnet_date(case.get("VerdictDt")),
                        "published_date": case.get("VerdictsDtString"),
                        "year": case.get("Year"),
                        "file_name": local_filename,
                        "file_size_bytes": file_size,
                        "download_url": url,
                        "local_path": str(local_path),
                    }
                )

                logger.info(
                    "Downloaded successfully: %s (%d bytes)",
                    local_filename,
                    file_size,
                )
                return

            except Exception as exc:
                logger.warning(
                    "Download failed (attempt %d) for %s: %s",
                    attempt,
                    local_filename,
                    exc,
                )
                time.sleep(2 ** attempt)

        logger.error("Abandoning download after retries: %s", local_filename)

    # ------------------------------------------------------------------ #
    # Orchestration
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """
        Execute the full download pipeline.
        """
        cases = self.fetch_verdicts()
        if not cases:
            logger.error("No verdicts retrieved — exiting")
            return

        jobs = self.create_download_jobs(cases)

        for index, job in enumerate(jobs, start=1):
            self.download_file(job, index, len(jobs))

        with open(METADATA_PATH, "w", encoding="utf-8") as fh:
            json.dump(self.metadata, fh, ensure_ascii=False, indent=2)

        logger.info("Metadata written to %s", METADATA_PATH)


# ============================================================================
# Entrypoint
# ============================================================================

if __name__ == "__main__":
    SupremeCourtDownloader().run()