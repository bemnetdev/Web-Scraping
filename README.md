# Israeli Supreme Court Verdict Scraper

This Python script fetches verdicts from the Israeli Supreme Court website for a specific date, filters for "important" verdicts, generates download URLs, and downloads the verdict files. It also maintains a metadata file for tracking.

---

## Features

- Fetch verdicts for a given date using the official API
- Filter by document type (`פסק-דין`) and importance (`מהותי בלבד`)
- Automatic retries for API and download requests
- Logging for monitoring all steps
- Saves metadata about each downloaded document
- Robust error handling to avoid script crashes

---

## Requirements

- Python 3.10+
- `requests` library

---

## Installation and Setup

1. **Clone the repository**:

```bash
git clone https://github.com/bemnetdev/Web-Scraping.git
cd Web Scraping
```

2. **Create a virtual environment (recommended):**

```bash
python -m venv venv
```

3. **Activate the virtual environment:**

- Windows:

```bash
venv\Scripts\activate
```

- macOS/Linux:

```bash
source venv/bin/activate
```

4. **Install dependencies:**

```bash
pip install -r requirements.txt
```

If requirements.txt does not exist, install manually:

```bash
pip install requests
```

## Usage

Run the scraper script from the terminal:

```bash
python app.py
```

- All downloaded documents will be stored in output/documents/.

- Metadata is saved to output/metadata.json.

- Logs are written to output/download_log.txt.

## Output Structure

```graphql
output/
├─ documents/       # downloaded verdict files
├─ verdicts.json    # raw JSON response from API
├─ metadata.json    # info about downloaded files
└─ download_log.txt # logs of the script
```

## Notes

- The script respects the "importance" filter (מהותי בלבד) and only downloads relevant verdicts.

- File names are generated as case_001_YYYY-MM-DD.pdf.

- You can change the target date by editing the PAYLOAD dictionary in the Python script.
