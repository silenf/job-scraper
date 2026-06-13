# Global Job Aggregator & Scraper

A robust Python command-line utility that scrapes and aggregates job listings (including job descriptions/JDs) from multiple boards: LinkedIn, Indeed, Glassdoor, Google Jobs, Naukri, and ZipRecruiter.

This project is optimized to run in a **WSL Ubuntu** environment, and features built-in bypasses for common scraping challenges like IP blocks, rate limits, page caps, and package-level parsing bugs.

---

## Features

- **Country-Wide Looping (`--country`)**: Bypasses LinkedIn's 140–250 guest result page cap by iterating through major cities/regions loaded from a central registry database (`locations.json`) and aggregating them in a single command.
- **Support for Multi-Country Queries**: You can pass a comma-separated list of country codes (e.g. `--country US,CA,AU`) or use the special keyword `--country all` to scrape all 30 registered countries (206 cities total) in one run.
- **Dynamic Deduplication**: Loads existing Job IDs from CSV and JSON output files at startup and filters out duplicate job posts in-memory to prevent redundant writes.
- **Progressive Saving**: Writes data progressively (appends to CSV and updates the JSON file) city-by-city so that scraped data is preserved even if the execution is interrupted.
- **Bypass IP Blocking**:
  - **Free Proxy Harvester & Verifier**: Automatically harvests proxies from `free-proxy-list.net` and validates them concurrently against the target job board (e.g. `linkedin.com` for LinkedIn) to ensure HTTPS tunneling works.
  - **Custom Proxy List Support**: Supports loading your custom rotating/residential proxies using the `--proxy-file` argument.
  - **Auto-Recovery Loop**: If a scrape fails due to proxy errors or connection resets, the script discards the active proxies, harvests/verifies a new batch, and retries the scrape automatically (up to 3 attempts).
  - **Sequential Throttling**: Loops through job boards and cities sequentially with a random delay (e.g. 5–15 seconds) to mimic natural browsing footprints.
- **Automatic Self-Healing**: Detects a known `NoneType` AttributeError in `python-jobspy` (v1.1.82) when parsing LinkedIn's `job_level` and patches the library file in-place on the fly, clearing Python's `__pycache__` to force immediate recompilation.
- **Normalized Output Formats**:
  - Automatically saves a companion JSON file named matching your output CSV.
  - Formats all JSON output keys in lowercase (e.g. `id` instead of `ID`, `job_url` instead of `JOB_URL`).
  - Serializes `datetime.date` columns returned by the scrapers to standard ISO strings (`YYYY-MM-DD`).

---

## File Structure

- `scrape_jobs.py`: The main scraping, self-healing, proxy handling, and country aggregation engine.
- `convert_json_keys.py`: A separate utility script to recursively convert dictionary keys in any JSON file to lowercase (leaving values intact).
- `locations.json`: The database of major cities/metropolitan areas across Western Europe, the Gulf, North America, and Asia-Pacific.
- `requirements.txt`: Python package requirements.

---

## Setup & Installation

Ensure you have Python 3.10+ installed in your WSL Ubuntu shell.

1. **Clone/copy the workspace files into your directory.**
2. **Install the required packages**:
   ```bash
   python3 -m pip install -r requirements.txt --break-system-packages
   ```
   *(Alternatively, create a virtual environment using `python3 -m venv venv` and install the requirements there).*

---

## How to Run the Scraper

### 1. Country Aggregator (Recommended)
To run a country-wide job aggregation (loops through cities in `locations.json`, scrapes, deduplicates, and saves to CSV and JSON companion files):

- **Single Country (e.g. United Kingdom)**:
  ```bash
  python3 scrape_jobs.py --keyword "software engineer" --country UK --results 140 --output uk_jobs.csv --sites linkedin
  ```
- **Multiple Countries (e.g. US and Canada)**:
  ```bash
  python3 scrape_jobs.py --keyword "software engineer" --country US,CA --results 140 --output us_ca_jobs.csv --sites linkedin
  ```
- **Scrape All Countries (206 cities across 30 countries)**:
  ```bash
  python3 scrape_jobs.py --keyword "software engineer" --country all --results 140 --output global_jobs.csv --sites linkedin
  ```

### 2. Bypass IP Blocks (Rotating Free Proxies)
To harvest free proxies automatically and rotate them to prevent rate limiting:
```bash
python3 scrape_jobs.py --keyword "software engineer" --country US --results 140 --output jobs.csv --use-proxies --max-proxies 30
```

### 3. Custom Proxy List
If you have custom paid/residential proxies, create a `proxies.txt` file (one proxy per line in the format `http://host:port` or `http://user:pass@host:port`) and run:
```bash
python3 scrape_jobs.py --keyword "software engineer" --country CA --results 100 --output jobs.csv --proxy-file proxies.txt
```

### 4. Single Location (Backward Compatible Mode)
To run a classic one-shot scrape for a single location string:
```bash
python3 scrape_jobs.py --keyword "software engineer" --location "Dallas, TX" --results 20 --output jobs.csv --sites linkedin,indeed
```

---

## Key-Conversion Utility

To recursively convert all dictionary keys in any arbitrary JSON file to lowercase:

- **Overwrite file in-place**:
  ```bash
  python3 convert_json_keys.py my_data.json
  ```
- **Write output to a new file**:
  ```bash
  python3 convert_json_keys.py my_data.json -o my_data_lowercase.json
  ```
