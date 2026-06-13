#!/usr/bin/env python3
import argparse
import concurrent.futures
import os
import random
import sys
import time
from bs4 import BeautifulSoup
import pandas as pd
import requests

# Import JobSpy
try:
    from jobspy import scrape_jobs
except ImportError:
    print("Error: python-jobspy is not installed. Please run 'pip install -r requirements.txt'")
    sys.exit(1)

def patch_jobspy_bug():
    """Checks for a known bug in the python-jobspy library (LinkedIn job_level NoneType AttributeError)
    and patches it in place in the active python site-packages.
    """
    try:
        import inspect
        import jobspy.linkedin
        
        # Get the path to jobspy/linkedin/__init__.py
        init_file = inspect.getfile(jobspy.linkedin)
        if init_file and os.path.exists(init_file):
            with open(init_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            target = 'job_level=job_details.get("job_level", "").lower(),'
            replacement = 'job_level=(job_details.get("job_level") or "").lower(),'
            pycache = os.path.join(os.path.dirname(init_file), "__pycache__")
            
            if target in content:
                print("[Self-Healing] Patching a known bug in python-jobspy package related to LinkedIn job_level...")
                new_content = content.replace(target, replacement)
                with open(init_file, "w", encoding="utf-8") as f:
                    f.write(new_content)
                if os.path.exists(pycache):
                    import shutil
                    shutil.rmtree(pycache)
                print("[Self-Healing] Successfully patched python-jobspy and cleared cache!")
            elif replacement in content:
                # If already patched on disk, ensure compiled cache is cleared to prevent stale execution
                if os.path.exists(pycache):
                    import shutil
                    shutil.rmtree(pycache)
    except Exception as e:
        print(f"[Self-Healing Warning] Could not check/patch jobspy library: {e}")

# Call the patcher
patch_jobspy_bug()

def harvest_free_proxies():
    """Scrapes free-proxy-list.net to retrieve a list of public HTTP/HTTPS proxies."""
    url = "https://free-proxy-list.net/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    proxies = []
    print("Retrieving free proxy list from free-proxy-list.net...")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch free proxies: HTTP {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try parsing the table
        table = soup.find('table', class_='table')
        if not table:
            # Fallback to finding textarea if any
            textarea = soup.find('textarea')
            if textarea:
                lines = textarea.text.strip().split('\n')
                for line in lines:
                    if line.strip() and not line.startswith('Updated'):
                        parts = line.strip().split(':')
                        if len(parts) == 2:
                            proxies.append(f"http://{parts[0]}:{parts[1]}")
                return proxies
            print("Could not find proxy table or textarea on free-proxy-list.net")
            return []
            
        tbody = table.find('tbody')
        if tbody:
            for row in tbody.find_all('tr'):
                cols = row.find_all('td')
                if len(cols) >= 2:
                    ip = cols[0].text.strip()
                    port = cols[1].text.strip()
                    # Column 6 is HTTPS (yes/no)
                    is_https = False
                    if len(cols) >= 7:
                        is_https = cols[6].text.strip().lower() == 'yes'
                    
                    scheme = "https" if is_https else "http"
                    proxies.append(f"{scheme}://{ip}:{port}")
    except Exception as e:
        print(f"Error harvesting free proxies: {e}")
    
    print(f"Harvested {len(proxies)} potential proxies.")
    return proxies

def check_proxy(proxy, test_url="https://www.google.com"):
    """Checks if a proxy is alive and responsive by requesting the test_url."""
    proxies_dict = {
        "http": proxy,
        "https": proxy
    }
    try:
        # Use GET request with a short timeout.
        # We accept any response from the server that indicates a successful connection/tunnel.
        response = requests.get(test_url, proxies=proxies_dict, timeout=3)
        # 2xx, 3xx, 403 (Forbidden by site), or 999 (LinkedIn block) mean the proxy tunnel works.
        # 5xx or connection exceptions mean the proxy server itself failed.
        if response.status_code < 500:
            return proxy
    except Exception:
        pass
    return None

def verify_proxies(proxies, limit=5, test_url="https://www.google.com"):
    """Concurrently verifies proxies against a target URL and returns up to 'limit' working ones."""
    if not proxies:
        return []
    print(f"Verifying proxies concurrently against {test_url} (looking for {limit} working ones)...")
    working_proxies = []
    
    # Run tests concurrently using a ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        future_to_proxy = {executor.submit(check_proxy, p, test_url): p for p in proxies}
        for future in concurrent.futures.as_completed(future_to_proxy):
            result = future.result()
            if result:
                working_proxies.append(result)
                print(f"  [+] Working proxy found: {result}")
                if len(working_proxies) >= limit:
                    break
                    
    print(f"Found {len(working_proxies)} active proxies out of tested ones.")
    return working_proxies

def scrape_jobs_safe(site, search_term, location, results_wanted, hours_old, 
                     proxies_list, country_indeed, linkedin_fetch_description, 
                     distance, job_type, is_remote, use_proxies=False, max_retries=3, max_proxies=20):
    """Safely wraps the JobSpy scrape_jobs call, retrying on proxy/timeout errors."""
    active_proxies = list(proxies_list) if proxies_list else []
    
    # Map the target site to a verification URL to test proxy connectivity to that specific site
    test_url = "https://www.google.com"
    if site == "linkedin":
        test_url = "https://www.linkedin.com"
    elif site == "indeed":
        test_url = "https://www.indeed.com"
    elif site == "glassdoor":
        test_url = "https://www.glassdoor.com"

    for attempt in range(1, max_retries + 1):
        print(f"\n[Scraper] Starting scrape for site '{site}' (Attempt {attempt}/{max_retries})...")
        
        # If proxies are requested but our list is empty (or got cleared due to failure), harvest new ones!
        if use_proxies and not active_proxies:
            print("  Active proxy list is empty. Harvesting new proxies...")
            harvested = harvest_free_proxies()
            active_proxies = verify_proxies(harvested, limit=max_proxies, test_url=test_url)
            if not active_proxies:
                print("  [!] Warning: No working free proxies found. Proceeding without proxies.")

        try:
            # Map parameters for scrape_jobs
            kwargs = {
                "site_name": [site],
                "search_term": search_term,
                "location": location,
                "results_wanted": results_wanted,
            }
            
            # Add optional args if they are provided
            if hours_old is not None:
                kwargs["hours_old"] = hours_old
            if country_indeed:
                kwargs["country_indeed"] = country_indeed
            if site == "linkedin" and linkedin_fetch_description:
                kwargs["linkedin_fetch_description"] = True
            if distance is not None:
                kwargs["distance"] = distance
            if job_type:
                kwargs["job_type"] = job_type
            if is_remote:
                kwargs["is_remote"] = True
            if active_proxies:
                kwargs["proxies"] = active_proxies
                print(f"  Using proxies: {active_proxies}")

            df = scrape_jobs(**kwargs)
            if df.empty:
                raise RuntimeError("No jobs returned (possible rate limit or bad proxy).")
            print(f"  [+] Site '{site}' scrape completed. Found {len(df)} jobs.")
            return df
        except Exception as e:
            err_msg = str(e)
            print(f"  [!] Error scraping site '{site}' on attempt {attempt}: {e}")
            import traceback
            traceback.print_exc()
            
            # Identify proxy or network timeout errors
            is_proxy_err = any(kw in err_msg.lower() for kw in [
                "proxy", "tunnel", "timeout", "connection pool", "connection reset", 
                "500 error", "502", "max retries exceeded", "read timed out", "no jobs returned"
            ])
            
            if is_proxy_err and active_proxies:
                print("  [!] Detected proxy or connection error. Discarding current proxies to force re-harvest/retry...")
                active_proxies = []  # Clear proxies so we harvest fresh ones next attempt
                time.sleep(random.uniform(3, 7))
            else:
                if not is_proxy_err:
                    print("  [!] Non-proxy error encountered. Skipping retries.")
                    break
                else:
                    time.sleep(random.uniform(3, 7))
                    
    return pd.DataFrame()

def save_new_jobs(new_df, csv_path, json_path):
    """Progressively appends new jobs to both CSV and JSON output files."""
    if new_df.empty:
        return

    # Make sure output directory exists
    out_dir = os.path.dirname(csv_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # 1. Save to CSV (append mode)
    file_exists = os.path.exists(csv_path)
    try:
        new_df.to_csv(csv_path, mode='a', index=False, header=not file_exists)
        print(f"  [+] Appended {len(new_df)} jobs to CSV: {csv_path}")
    except Exception as e:
        print(f"  [!] Error appending to CSV: {e}")

    # 2. Save to JSON (read, append, write)
    try:
        import json
        import datetime
        new_records = new_df.to_dict(orient='records')
        
        lowercase_new_records = []
        for record in new_records:
            clean_record = {}
            for k, v in record.items():
                k_lower = str(k).lower()
                if pd.isna(v):
                    clean_record[k_lower] = None
                elif isinstance(v, (datetime.date, datetime.datetime)):
                    clean_record[k_lower] = v.isoformat()
                else:
                    clean_record[k_lower] = v
            lowercase_new_records.append(clean_record)

        existing_records = []
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    existing_records = json.load(f)
                    if not isinstance(existing_records, list):
                        existing_records = []
            except Exception:
                existing_records = []

        combined_records = existing_records + lowercase_new_records
        
        # Ensure all keys in combined_records are lowercase (for consistency with previous runs)
        final_records = []
        for record in combined_records:
            if isinstance(record, dict):
                clean_rec = {}
                for k, v in record.items():
                    clean_rec[str(k).lower()] = v
                final_records.append(clean_rec)
            else:
                final_records.append(record)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(final_records, f, indent=2, ensure_ascii=False)
        print(f"  [+] Rewrote JSON with {len(final_records)} total jobs: {json_path}")
    except Exception as e:
        print(f"  [!] Error writing to JSON: {e}")

def main():
    parser = argparse.ArgumentParser(description="Multi-board Job Scraper with Proxy Bypass")
    parser.add_argument("-k", "--keyword", default="software engineer", help="Job search keyword/title")
    parser.add_argument("-l", "--location", default="Remote", help="Job location")
    parser.add_argument("-r", "--results", type=int, default=10, help="Max results to fetch per job board")
    parser.add_argument("-s", "--sites", default="linkedin,indeed,google,zip_recruiter,naukri", 
                        help="Comma-separated list of sites to scrape (linkedin,indeed,glassdoor,google,zip_recruiter,naukri,bayt,bdjobs)")
    parser.add_argument("-o", "--output", default="jobs.csv", help="Output filepath (CSV or Excel)")
    
    # Anti-blocking options
    parser.add_argument("--use-proxies", action="store_true", help="Harvest and rotate free proxies")
    parser.add_argument("--proxy-file", help="Path to a text file containing custom proxies (one per line)")
    parser.add_argument("--no-sequential", dest="sequential", action="store_false", 
                        help="Do not scrape sites sequentially (disables delay between sites)")
    parser.add_argument("--delay-min", type=int, default=5, help="Minimum seconds of delay between sequential scrapes")
    parser.add_argument("--delay-max", type=int, default=15, help="Maximum seconds of delay between sequential scrapes")
    
    # Specific filter parameters
    parser.add_argument("--hours-old", type=int, help="Only fetch jobs posted in the last N hours")
    parser.add_argument("--distance", type=int, help="Search radius/distance in miles")
    parser.add_argument("--job-type", choices=["fulltime", "parttime", "contract", "internship", "temporary"], 
                        help="Job type filter")
    parser.add_argument("--is-remote", action="store_true", help="Filter for remote jobs only")
    parser.add_argument("--country-indeed", default="usa", help="Indeed/Glassdoor country code (e.g., 'usa', 'india', 'uk')")
    parser.add_argument("--no-fetch-jd", dest="fetch_jd", action="store_false", 
                        help="Disable fetching of full job descriptions (faster but no JDs for LinkedIn)")
    parser.add_argument("--max-proxies", type=int, default=20, 
                        help="Maximum number of verified proxies to harvest and rotate (default: 20)")
    parser.add_argument("--country", help="Country code to scrape (e.g. US, AU, CA, UK). Loops over major cities.")
    parser.add_argument("--location-file", default="locations.json", help="Path to locations JSON file (default: locations.json)")

    args = parser.parse_args()

    # Parse site names
    sites = [s.strip().lower() for s in args.sites.split(",") if s.strip()]
    if not sites:
        print("Error: No job boards specified to scrape.")
        sys.exit(1)

    print("=" * 60)
    print("Starting Job Board Scraper")
    print(f"Keyword:      {args.keyword}")
    print(f"Location:     {args.location}")
    print(f"Max Results:  {args.results} per board")
    print(f"Target Sites: {', '.join(sites)}")
    print("=" * 60)

    # Resolve proxies
    proxies_list = []
    if args.proxy_file:
        if os.path.exists(args.proxy_file):
            print(f"Reading proxies from file: {args.proxy_file}")
            with open(args.proxy_file, "r") as f:
                proxies_list = [line.strip() for line in f if line.strip()]
            print(f"Loaded {len(proxies_list)} custom proxies.")
        else:
            print(f"Error: Proxy file '{args.proxy_file}' does not exist.")
            sys.exit(1)
    elif args.use_proxies:
        harvested = harvest_free_proxies()
        proxies_list = verify_proxies(harvested, limit=args.max_proxies)
        if not proxies_list:
            print("[!] Warning: No working free proxies found. Falling back to direct requests.")

    # Derive JSON output filename
    csv_output_path = args.output
    if csv_output_path.endswith(".csv"):
        json_output_path = csv_output_path[:-4] + ".json"
    elif csv_output_path.endswith(".xlsx"):
        json_output_path = csv_output_path[:-5] + ".json"
    else:
        json_output_path = csv_output_path + ".json"

    # Load existing IDs for deduplication state
    existing_ids = set()
    if os.path.exists(csv_output_path):
        try:
            temp_df = pd.read_csv(csv_output_path)
            if 'ID' in temp_df.columns:
                existing_ids.update(temp_df['ID'].dropna().astype(str).tolist())
            elif 'id' in temp_df.columns:
                existing_ids.update(temp_df['id'].dropna().astype(str).tolist())
            print(f"Loaded {len(existing_ids)} existing Job IDs from CSV.")
        except Exception as e:
            print(f"Warning: Could not read existing Job IDs from CSV: {e}")

    if os.path.exists(json_output_path):
        try:
            import json
            with open(json_output_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
                if isinstance(json_data, list):
                    for job in json_data:
                        if 'ID' in job:
                            existing_ids.add(str(job['ID']))
                        elif 'id' in job:
                            existing_ids.add(str(job['id']))
            print(f"Loaded existing Job IDs from JSON. Total unique tracking IDs: {len(existing_ids)}")
        except Exception as e:
            print(f"Warning: Could not read existing Job IDs from JSON: {e}")

    # Load cities list if country code is selected
    cities = []
    if args.country:
        if not os.path.exists(args.location_file):
            print(f"Error: Location file '{args.location_file}' does not exist.")
            sys.exit(1)
        try:
            import json
            with open(args.location_file, "r", encoding="utf-8") as f:
                loc_db = json.load(f)
            
            loc_db_upper = {k.upper(): v for k, v in loc_db.items()}
            
            if args.country.strip().lower() == "all":
                # Load all countries
                for code, city_list in loc_db.items():
                    cities.extend(city_list)
                    print(f"Loaded {len(city_list)} cities for country code '{code}' from {args.location_file}.")
            else:
                country_codes = [c.strip().upper() for c in args.country.split(",") if c.strip()]
                for code in country_codes:
                    if code in loc_db_upper:
                        cities.extend(loc_db_upper[code])
                        print(f"Loaded {len(loc_db_upper[code])} cities for country code '{code}' from {args.location_file}.")
                    else:
                        print(f"Error: Country code '{code}' not found in location file. Available: {', '.join(loc_db.keys())}")
                        sys.exit(1)
            print(f"Total cities to scrape across all countries: {len(cities)}")
        except Exception as e:
            print(f"Error reading location file: {e}")
            sys.exit(1)

    # Execute scrapers
    if cities:
        # Loop over cities (country-level aggregation)
        for c_idx, city in enumerate(cities):
            print("\n" + "=" * 60)
            print(f"Processing City {c_idx+1}/{len(cities)}: {city} (Country: {args.country.upper()})")
            print("=" * 60)
            
            for s_idx, site in enumerate(sites):
                # Add delay before scraping if it's not the very first request
                if c_idx > 0 or s_idx > 0:
                    delay = random.uniform(args.delay_min, args.delay_max)
                    print(f"\nWaiting {delay:.2f} seconds before next request to avoid IP block...")
                    time.sleep(delay)
                
                df = scrape_jobs_safe(
                    site=site,
                    search_term=args.keyword,
                    location=city,
                    results_wanted=args.results,
                    hours_old=args.hours_old,
                    proxies_list=proxies_list,
                    country_indeed=args.country_indeed,
                    linkedin_fetch_description=args.fetch_jd,
                    distance=args.distance,
                    job_type=args.job_type,
                    is_remote=args.is_remote,
                    use_proxies=args.use_proxies,
                    max_proxies=args.max_proxies
                )
                
                if not df.empty:
                    df.columns = [col.upper() for col in df.columns]
                    
                    # Deduplicate in-memory
                    unique_df = df[~df['ID'].astype(str).isin(existing_ids)]
                    if not unique_df.empty:
                        new_ids = unique_df['ID'].astype(str).tolist()
                        existing_ids.update(new_ids)
                        print(f"  [+] Found {len(unique_df)} new unique jobs in {city} (out of {len(df)} scraped).")
                        save_new_jobs(unique_df, csv_output_path, json_output_path)
                    else:
                        print(f"  [~] Scraped {len(df)} jobs in {city}, but all were duplicates.")
        
        print("\n" + "=" * 60)
        print(f"Country-level aggregation completed. Output files: {csv_output_path} and {json_output_path}")
        print("=" * 60)

    else:
        # Single-location scraping (Backward compatibility)
        print("\nRunning single-location scrape for: " + args.location)
        all_dfs = []
        
        if args.sequential:
            for s_idx, site in enumerate(sites):
                if s_idx > 0:
                    delay = random.uniform(args.delay_min, args.delay_max)
                    print(f"\nWaiting {delay:.2f} seconds before scraping next site...")
                    time.sleep(delay)
                
                df = scrape_jobs_safe(
                    site=site,
                    search_term=args.keyword,
                    location=args.location,
                    results_wanted=args.results,
                    hours_old=args.hours_old,
                    proxies_list=proxies_list,
                    country_indeed=args.country_indeed,
                    linkedin_fetch_description=args.fetch_jd,
                    distance=args.distance,
                    job_type=args.job_type,
                    is_remote=args.is_remote,
                    use_proxies=args.use_proxies,
                    max_proxies=args.max_proxies
                )
                if not df.empty:
                    all_dfs.append(df)
        else:
            print("\nScraping all sites concurrently...")
            try:
                kwargs = {
                    "site_name": sites,
                    "search_term": args.keyword,
                    "location": args.location,
                    "results_wanted": args.results,
                }
                if args.hours_old is not None:
                    kwargs["hours_old"] = args.hours_old
                if args.country_indeed:
                    kwargs["country_indeed"] = args.country_indeed
                if args.fetch_jd:
                    kwargs["linkedin_fetch_description"] = True
                if args.distance is not None:
                    kwargs["distance"] = args.distance
                if args.job_type:
                    kwargs["job_type"] = args.job_type
                if args.is_remote:
                    kwargs["is_remote"] = True
                if proxies_list:
                    kwargs["proxies"] = proxies_list

                df = scrape_jobs(**kwargs)
                if not df.empty:
                    all_dfs.append(df)
            except Exception as e:
                print(f"[!] Error during concurrent scrape: {e}")
                
        # Save results for single-location scrape
        if all_dfs:
            final_df = pd.concat(all_dfs, ignore_index=True)
            final_df.columns = [col.upper() for col in final_df.columns]
            
            # Deduplicate against existing data
            unique_df = final_df[~final_df['ID'].astype(str).isin(existing_ids)]
            if not unique_df.empty:
                print(f"\nFound {len(unique_df)} unique new jobs (out of {len(final_df)} scraped).")
                save_new_jobs(unique_df, csv_output_path, json_output_path)
            else:
                print("\n[~] Scraped jobs are already present in the output files (all duplicates).")
        else:
            print("\n[!] Scraping finished, but no jobs were retrieved.")

if __name__ == "__main__":
    main()
