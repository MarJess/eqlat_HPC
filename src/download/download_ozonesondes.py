import io
import os
import time

import numpy as np
import pandas as pd
import xarray as xr
#import xesmf as xe
from bs4 import BeautifulSoup


try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# NOAA GML's aftp archive (and similar government data servers) will reset
# the connection ("Remote end closed connection without response") for
# requests that don't look like a browser, and occasionally under transient
# load even with a browser UA. A realistic User-Agent + retry-with-backoff
# works around both.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _get_with_retry(url, max_retries=5, backoff=2, timeout=60, **kwargs):
    """
    GET a URL with a browser-like User-Agent, retrying on connection errors.

    Args:
        url (str): URL to fetch.
        max_retries (int): Number of attempts before giving up.
        backoff (int): Base for exponential backoff between retries (seconds).
        timeout (int): Per-request timeout in seconds.
        **kwargs: Passed through to requests.get().

    Returns:
        requests.Response

    Raises:
        The last requests.exceptions.ConnectionError if all retries fail.
    """
    if not HAS_REQUESTS:
        raise ImportError("The 'requests' package is required: pip install requests")

    headers = {**_BROWSER_HEADERS, **kwargs.pop("headers", {})}

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return requests.get(url, headers=headers, timeout=timeout, **kwargs)
        except requests.exceptions.ConnectionError as e:
            last_exc = e
            wait = backoff ** attempt
            print(f"  Connection error (attempt {attempt}/{max_retries}) for {url}: {e}")
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)

    raise last_exc


def get_o3_file_paths(url, year=None):
    """
    Scrapes a webpage for links to ozone sonde data files (.dat).

    This function fetches the HTML content of the provided URL, parses it to find
    all anchor tags, and filters for links ending in the '.dat' extension.
    It converts relative paths into absolute URLs.

    Args:
        url (str): The destination URL containing the ozone data links.
        year (str, optional): The year of interest for ozone data. If None,
            all '.dat' files found at the URL are returned (no year filter).

    Returns:
        list: A list of strings, where each string is a full URL path
            to a discovered '.dat' file. Returns an empty list if no
            files are found or if the request fails.
    """
    if not HAS_REQUESTS:
        raise ImportError("The 'requests' package is required: pip install requests")

    exts = ('.dat',)

    response = _get_with_retry(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')

    files = [
        a['href']
        for a in soup.find_all('a', href=True)
        if a['href'].endswith(exts) and (year is None or year in a['href'])
    ]

    print(f"Found {len(files)} files." + (f" (year={year})" if year else ""))

    return files


def _has_gps_lat_lon(columns):
    """
    Check whether a (possibly MultiIndex) set of column labels contains
    GPS-derived latitude/longitude columns.

    NOAA Boulder native-resolution ozonesonde files only carry per-scan
    'GPS Lat' / 'GPS Lon' columns once GPS-based radiosondes were in use;
    older files only have a single launch-site lat/lon in the header.
    This checks the actual data columns (not the header metadata), since
    we need per-scan position for equivalent-latitude trajectory matching.

    Args:
        columns: iterable of column labels; each label may be a string or
            a tuple (as in a pandas MultiIndex).

    Returns:
        bool: True if a GPS latitude AND a GPS longitude column were found.
    """
    flat = []
    for c in columns:
        if isinstance(c, tuple):
            flat.append(" ".join(str(x) for x in c))
        else:
            flat.append(str(c))

    text = " | ".join(flat).lower()

    return "gps" in text and "lat" in text and "lon" in text


def read_noaa_O3_url(base_path, file_name, to_csv=True, o3sonde_dir='.', require_gps=False):
    """
    Downloads, parses, and cleans NOAA ozonesonde data from a specified URL.

    This function checks for locally cached versions of the data based on the date
    string in the filename. If not found, it downloads the raw text, extracts
    flight metadata (location, coordinates, flight number), flattens multi-index
    headers, and converts GMT time strings into localized datetime objects.

    Args:
        base_path (str): The root URL or directory path where the raw file resides.
        file_name (str): The specific filename (e.g., 'bu_2023_05_12_18.l100').
            Expects underscores separating the date components at indices 1, 2, and 3.
        to_csv (bool): If True, saves the processed DataFrame to a CSV file.
            Defaults to True.
        o3sonde_dir (str): The local directory path for checking existing files
            and saving new output. Defaults to the current directory ('.').
        require_gps (bool): If True, profiles without per-scan GPS latitude/
            longitude columns are skipped entirely (not saved) and this
            function returns None. Defaults to False (keep everything, as
            before). Note: if a same-date CSV was already cached by an
            earlier non-GPS-filtered run, that cached file is returned as-is
            without re-checking for GPS columns.

    Returns:
        dict or None: None if `require_gps` is True and no GPS lat/lon
            columns were found. Otherwise a dictionary with keys:
            - 'date': (str) The ISO-formatted date string (YYYY-MM-DD).
            - 'data': (pd.DataFrame) The cleaned ozone profile data with
              unified headers and 'DATETIME GMT' column.
            - 'flight_nr', 'location', 'launch_lat', 'launch_lon', 'has_gps'
    """
    if not HAS_REQUESTS:
        raise ImportError("The 'requests' package is required: pip install requests")

    parts = file_name.split('_')
    date_str = "-".join(parts[1:4])

    os.makedirs(o3sonde_dir, exist_ok=True)

    # Check for any existing file matching this date to avoid downloading again.
    if to_csv:
        existing_files = [f for f in os.listdir(o3sonde_dir) if date_str in f and f.endswith('.csv')]
        if existing_files:
            print(f"Skipping: Data for {date_str} already exists locally ({existing_files[0]}).")
            cached = pd.read_csv(os.path.join(o3sonde_dir, existing_files[0]))
            return {
                'date': date_str,
                'data': cached,
                'flight_nr': cached['flight_nr'].iloc[0] if 'flight_nr' in cached.columns else None,
                'location': cached['location'].iloc[0] if 'location' in cached.columns else None,
                'launch_lat': cached['launch_lat'].iloc[0] if 'launch_lat' in cached.columns else None,
                'launch_lon': cached['launch_lon'].iloc[0] if 'launch_lon' in cached.columns else None,
                'has_gps': bool(cached['has_gps'].iloc[0]) if 'has_gps' in cached.columns else None,
            }

    # DOWNLOAD (only happens if file doesn't exist locally)
    full_url = base_path.rstrip('/') + '/' + file_name.lstrip('/')
    response = _get_with_retry(full_url)
    response.raise_for_status()

    # PARSE METADATA
    lines = response.text.splitlines()
    data_start_idx = 0
    flight_nr, location, longitude, latitude = "UNK", "UNK", 0, 0

    for i, line in enumerate(lines):
        if 'Flight number' in line:
            flight_nr = line.split(' ')[-1].strip()
        elif 'Location' in line:
            location = line.split(' ')[-2].strip().rstrip(',')
            print(location)
        elif 'Longitude' in line:
            longitude = line.split(' ')[-1].strip()
        elif 'Latitude' in line:
            latitude = line.split(' ')[-1].strip()
        elif "[min]" in line:
            data_start_idx = i - 2
            break

    # PARSE DATA — reuse already-downloaded text via StringIO (no second HTTP request)
    df = pd.read_csv(
        io.StringIO(response.text),
        skiprows=data_start_idx,
        header=[0, 1],
        sep=',',
        skipinitialspace=True,
        engine='python'
    )

    # Check for per-scan GPS lat/lon BEFORE flattening (needs the MultiIndex columns)
    has_gps = _has_gps_lat_lon(df.columns)

    if require_gps and not has_gps:
        print(f"Skipping {file_name}: no GPS latitude/longitude columns found (date {date_str}).")
        return None

    # Save time column before flattening the MultiIndex
    time_col = df['Time GMT'].iloc[:, 0]

    # Flatten MultiIndex columns — must happen before adding single-level columns
    df.columns = [col[0] + ' ' + col[1] for col in df.columns]
    df = df.replace(99999, np.nan)

    # Add derived columns after flattening to avoid index mismatch
    df['DATETIME GMT'] = pd.to_datetime(date_str + ' ' + time_col)
    df['launch_lat'] = latitude
    df['launch_lon'] = longitude
    df['flight_nr'] = flight_nr
    df['location'] = location
    df['has_gps'] = has_gps

    # SAVE
    if to_csv:
        out_name = f'ozonesonde_{flight_nr}_{location}_{"".join(parts[1:4])}.csv'
        df.to_csv(os.path.join(o3sonde_dir, out_name), index=False)
        print(f"Successfully processed and saved: {out_name}  (GPS: {has_gps})")

    return {
        'date': date_str,
        'data': df,
        'flight_nr': flight_nr,
        'location': location,
        'launch_lat': latitude,
        'launch_lon': longitude,
        'has_gps': has_gps,
    }


# ---------------------------------------------------------------------------
#  Range download with GPS filtering + manifest
# ---------------------------------------------------------------------------

def download_ozonesondes_gps_range(url, outdir, year_start, year_end, manifest_path=None):
    """
    Download NOAA ozonesonde profiles for every year in [year_start, year_end]
    that contain per-scan GPS latitude/longitude columns, and write a manifest
    of the resulting flight dates.

    Profiles without GPS lat/lon (older, pre-GPS-radiosonde files) are skipped
    entirely — not downloaded to CSV. The manifest is intended to drive
    matching ERA5 / MERRA-2 reanalysis downloads for equivalent-latitude
    calculations (see download_ERA_5.py / download_MERRA_2_new.py --dates-file).

    Args:
        url (str): Base URL of the NOAA ozonesonde native-resolution directory.
        outdir (str): Directory to save per-profile CSVs.
        year_start (int): First year to scan (inclusive).
        year_end (int): Last year to scan (inclusive).
        manifest_path (str, optional): Path to write the CSV manifest of
            GPS-equipped flight dates. If None, no manifest file is written.

    Returns:
        pd.DataFrame: One row per GPS-equipped flight, columns
            ['date', 'flight_nr', 'location', 'launch_lat', 'launch_lon'].
    """
    os.makedirs(outdir, exist_ok=True)

    records = []
    for year in range(year_start, year_end + 1):
        print(f"--- Scanning {year} ---")
        files = get_o3_file_paths(url, str(year))

        for file_name in files:
            try:
                result = read_noaa_O3_url(
                    url, file_name, to_csv=True, o3sonde_dir=outdir, require_gps=True
                )
            except Exception as e:
                print(f"  ERROR {file_name}: {e}")
                continue

            if result is not None:
                records.append({
                    'date': result['date'],
                    'flight_nr': result.get('flight_nr'),
                    'location': result.get('location'),
                    'launch_lat': result.get('launch_lat'),
                    'launch_lon': result.get('launch_lon'),
                })

    dates_df = pd.DataFrame(
        records, columns=['date', 'flight_nr', 'location', 'launch_lat', 'launch_lon']
    )
    if not dates_df.empty:
        dates_df = dates_df.drop_duplicates(subset='date').sort_values('date').reset_index(drop=True)

    if manifest_path:
        manifest_dir = os.path.dirname(manifest_path)
        if manifest_dir:
            os.makedirs(manifest_dir, exist_ok=True)
        dates_df.to_csv(manifest_path, index=False)
        print(f"Wrote manifest with {len(dates_df)} GPS-equipped flight dates to {manifest_path}")

    return dates_df


# ---------------------------------------------------------------------------
#  CLI entry point
# ---------------------------------------------------------------------------


def main():
    """
    Download NOAA ozonesonde profiles for a range of years, keeping only
    profiles that contain per-scan GPS latitude/longitude, and write a
    manifest CSV of the resulting flight dates.
    """
    import argparse

    default_url = (
        "https://gml.noaa.gov/aftp/data/ozwv/Ozonesonde/"
        "Boulder,%20Colorado/Native%20Resolution%20(60s,%207s,%201s)/"
    )

    parser = argparse.ArgumentParser(
        description="Download NOAA ozonesonde profiles with GPS lat/lon for a range of years."
    )
    parser.add_argument("--year-start", type=int, required=True, help="First year to download, e.g. 2005")
    parser.add_argument("--year-end", type=int, required=True, help="Last year to download (inclusive), e.g. 2025")
    parser.add_argument(
        "--url", type=str, default=default_url,
        help="Base URL to NOAA ozonesonde native-resolution data (default: Boulder, Colorado)"
    )
    parser.add_argument(
        "--outdir", type=str,
        default=os.environ.get("DATA", ".") + "/ozonesonde",
        help="Output directory for per-profile CSVs (default: $DATA/ozonesonde)"
    )
    parser.add_argument(
        "--manifest", type=str, default=None,
        help="Path for the CSV manifest of GPS-equipped flight dates "
             "(default: <outdir>/gps_dates_manifest.csv)"
    )
    args = parser.parse_args()

    manifest_path = args.manifest or os.path.join(args.outdir, "gps_dates_manifest.csv")

    print(f"=== Ozonesonde GPS download: {args.year_start}-{args.year_end} ===")
    print(f"    URL      : {args.url}")
    print(f"    Outdir   : {args.outdir}")
    print(f"    Manifest : {manifest_path}")

    dates_df = download_ozonesondes_gps_range(
        args.url, args.outdir, args.year_start, args.year_end, manifest_path=manifest_path
    )

    print(f"=== Finished: {len(dates_df)} GPS-equipped profiles ({args.year_start}-{args.year_end}) ===")


if __name__ == "__main__":
    main()


# # Investigate the numbver of profiles for three different location in the USA
# boulder_url = "https://gml.noaa.gov/aftp/data/ozwv/Ozonesonde/Boulder,%20Colorado/Native%20Resolution%20(60s,%207s,%201s)/"
# trinidad_url = "https://gml.noaa.gov/aftp/data/ozwv/Ozonesonde/Trinidad%20Head,%20California/Native%20Resolution/"
# huntsville_url = "https://gml.noaa.gov/aftp/data/ozwv/Ozonesonde/Huntsville,%20Alabama/1%20Second%20Data%20Files/"

# boulder_files = get_o3_file_paths(boulder_url)
# trinidad_files = get_o3_file_paths(trinidad_url)
# huntsville_files = get_o3_file_paths(huntsville_url)
