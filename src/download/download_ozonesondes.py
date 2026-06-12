import io
import os

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


def get_o3_file_paths(url, year):
    """
    Scrapes a webpage for links to ozone sonde data files (.dat).

    This function fetches the HTML content of the provided URL, parses it to find
    all anchor tags, and filters for links ending in the '.dat' extension.
    It converts relative paths into absolute URLs.

    Args:
        url (str): The destination URL containing the ozone data links.
        year (str): The year of interest for ozone data.

    Returns:
        list: A list of strings, where each string is a full URL path
            to a discovered '.dat' file. Returns an empty list if no
            files are found or if the request fails.
    """
    if not HAS_REQUESTS:
        raise ImportError("The 'requests' package is required: pip install requests")

    exts = ('.dat',)

    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    files = [
        a['href']
        for a in soup.find_all('a', href=True)
        if a['href'].endswith(exts) and year in a['href']
    ]

    print(f"Found {len(files)} files.")

    return files


def read_noaa_O3_url(base_path, file_name, to_csv=True, o3sonde_dir='.'):
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

    Returns:
        dict: A dictionary containing two keys:
            - 'date': (str) The ISO-formatted date string (YYYY-MM-DD).
            - 'data': (pd.DataFrame) The cleaned ozone profile data with
              unified headers and 'DATETIME_GMT' column.
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
            return {'date': date_str, 'data': pd.read_csv(os.path.join(o3sonde_dir, existing_files[0]))}

    # DOWNLOAD (only happens if file doesn't exist locally)
    full_url = base_path.rstrip('/') + '/' + file_name.lstrip('/')
    response = requests.get(full_url)
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

    # Save time column before flattening the MultiIndex
    time_col = df['Time GMT'].iloc[:, 0]

    # Flatten MultiIndex columns — must happen before adding single-level columns
    df.columns = [col[0] + ' ' + col[1] for col in df.columns]
    df = df.replace(99999, np.nan)

    # Add derived columns after flattening to avoid index mismatch
    df['DATETIME GMT'] = pd.to_datetime(date_str + ' ' + time_col)
    df['launch_lat'] = latitude
    df['launch_lon'] = longitude

    # SAVE
    if to_csv:
        out_name = f'ozonesonde_{flight_nr}_{location}_{"".join(parts[1:4])}.csv'
        df.to_csv(os.path.join(o3sonde_dir, out_name), index=False)
        print(f"Successfully processed and saved: {out_name}")

    return {'date': date_str, 'data': df}


# ---------------------------------------------------------------------------
#  CLI entry point
# ---------------------------------------------------------------------------


def main():
    """
    Download Ozonsonde data from on location, given by the url (NOAA)
    and a time frame
    """
    import argparse
    import calendar

    parser = argparse.ArgumentParser(
        description="Download NOAA Ozonesonde for a given time frame."
    )

    parser.add_argument("year", type=str, help="Year to download, e.g. 2023")
    parser.add_argument(
        "--url", type=str,
        help="Base URL to NOAA Ozonesonde data"
    )
    parser.add_argument(
        "--outdir", type=str,
        default=os.environ.get("DATA", ".") + "/ozonesonde",
        help="Output directory (default: $DATA/ozonesonde)"
    )
    args = parser.parse_args()

    year   = args.year
    outdir = args.outdir
    url    = args.url

    os.makedirs(outdir, exist_ok=True)

    tmp_files = get_o3_file_paths(url, year)

    print(tmp_files)

    for file in tmp_files:
        read_noaa_O3_url(url, file, to_csv=True, o3sonde_dir=outdir)

    print(f"=== Finished Ozonesonde download for {year} ===")

if __name__ == "__main__":
    main()


# # Investigate the numbver of profiles for three different location in the USA
# boulder_url = "https://gml.noaa.gov/aftp/data/ozwv/Ozonesonde/Boulder,%20Colorado/Native%20Resolution%20(60s,%207s,%201s)/"
# trinidad_url = "https://gml.noaa.gov/aftp/data/ozwv/Ozonesonde/Trinidad%20Head,%20California/Native%20Resolution/"
# huntsville_url = "https://gml.noaa.gov/aftp/data/ozwv/Ozonesonde/Huntsville,%20Alabama/1%20Second%20Data%20Files/"

# boulder_files = get_o3_file_paths(boulder_url)
# trinidad_files = get_o3_file_paths(trinidad_url)
# huntsville_files = get_o3_file_paths(huntsville_url)
