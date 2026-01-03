import json
import logging
import time
from pathlib import Path
from typing import List, Dict
from urllib.parse import urlparse, parse_qs

import requests
from requests.adapters import HTTPAdapter, Retry

# ---------------- CONFIG ----------------
API_URL = "https://supremedecisions.court.gov.il/Home/SearchVerdicts"

OUTPUT_DIR = Path("output")
DOCS_DIR = OUTPUT_DIR / "documents"
METADATA_FILE = OUTPUT_DIR / "metadata.json"
LOG_FILE = OUTPUT_DIR / "download_log.txt"

# Create directories
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/117.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://supremedecisions.court.gov.il/Pages/fullsearch.aspx",
}

# Payload to fetch verdicts for a single day with importance = "מהותי בלבד"
PAYLOAD = {
    "document": {
        "PublishFrom": "2025-09-30T21:00:00.000Z",
        "PublishTo": "2025-09-30T21:00:00.000Z",
        "Type": [{"parent": 0, "value": 2, "text": "פסק-דין"}],
        "Technical": 0, # "מהותי בלבד"
        "dateType": 2,
        "fromPages": None,
        "toPages": None,
        "CodeTypes": [2]
    },
    "AllSubjects": [{"Subject": None, "SubSubject": None, "SubSubSubject": None}],
    "Counsel": [],
    "Parties": [],
    "SearchText": [],
    "lan": "1"
}

DOWNLOAD_BASE_URL = "https://supremedecisions.court.gov.il/Home/Download"

# ---------------- SCRAPER ----------------
class SupremeCourtDownloader:
    def __init__(self):
        self.session = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.headers.update(HEADERS)
        self.metadata: List[Dict] = []

    def fetch_verdicts(self, payload: dict) -> dict:
        """Fetch verdicts JSON from API."""
        try:
            logging.info("Fetching verdicts from API...")
            response = self.session.post(API_URL, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            logging.info(f"Fetched {len(data.get('data', []))} verdicts")
            return data
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching API data: {e}")
        except json.JSONDecodeError:
            logging.error(f"Failed to decode JSON. Response: {response.text[:500]}")
        return {}

    def create_filepaths(self, data: dict) -> List[str]:
        """Create download URLs from API response."""
        DOCUMENT_URLS = []
        for doc in data.get("data", []):
            path_for_web = doc.get("PathForWeb")
            file_name = doc.get("FileName")
            if path_for_web and file_name:
                url = f"{DOWNLOAD_BASE_URL}?path={path_for_web}&fileName={file_name}&type=4"
                DOCUMENT_URLS.append(url)
        logging.info(f"Created {len(DOCUMENT_URLS)} download URLs")
        return DOCUMENT_URLS

    @staticmethod
    def extract_date_from_path(path: str) -> str:
        parts = path.split("/")
        return f"{parts[1]}-{parts[2]}-{parts[3].zfill(2)}"

    @staticmethod
    def infer_extension(doc_type: str) -> str:
        return {"4": "pdf", "3": "docx"}.get(doc_type, "bin")

    def download_document(self, url: str, index: int, total: int):
        """Download a single document with retries and log progress."""
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        path = qs.get("path", ["unknown"])[0]
        file_hash = qs.get("fileName", ["unknown"])[0]
        doc_type = qs.get("type", ["4"])[0]

        date = self.extract_date_from_path(path)
        ext = self.infer_extension(doc_type)
        filename = f"case_{index:03d}_{date}.{ext}"
        file_path = DOCS_DIR / filename

        for attempt in range(5):
            try:
                logging.info(f"Downloading ({index}/{total}) Attempt {attempt+1}: {filename}")
                with self.session.get(url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(file_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                logging.info(f"Downloaded ({index}/{total}) successfully: {filename}")
                # Save metadata
                self.metadata.append({
                    "index": index,
                    "date": date,
                    "file_type": ext,
                    "source_url": url,
                    "local_path": str(file_path),
                    "server_file_hash": file_hash
                })
                return
            except requests.exceptions.RequestException as e:
                logging.warning(f"Attempt {attempt+1} failed for {filename}: {e}")
                time.sleep(2 ** attempt)  # exponential backoff
        logging.error(f"Failed to download ({index}/{total}) {filename} after 5 attempts")

    def save_metadata(self):
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        logging.info(f"Saved metadata to {METADATA_FILE}")

    def run(self):
        data = self.fetch_verdicts(PAYLOAD)
        if not data:
            logging.error("No verdict data fetched. Exiting.")
            return

        DOCUMENT_URLS = self.create_filepaths(data)
        total = len(DOCUMENT_URLS)
        for i, url in enumerate(DOCUMENT_URLS, start=1):
            self.download_document(url, i, total)
        self.save_metadata()


# ---------------- ENTRYPOINT ----------------
if __name__ == "__main__":
    downloader = SupremeCourtDownloader()
    downloader.run()
