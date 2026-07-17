"""
Download ERA5 Potential Vorticity on pressure surfaces from CDS.

Prerequisites:
    1. Register at https://cds.climate.copernicus.eu
    2. Install the CDS API client:
           pip install cdsapi
    3. Create ~/.cdsapirc with your API key:
           url: https://cds.climate.copernicus.eu/api
           key: <your-uid>:<your-api-key>

"""

import argparse
import os
from pathlib import Path

try:
    import cdsapi
    HAS_CDSAPI = True
except ImportError:
    HAS_CDSAPI = False
    print("WARNING: cdsapi not installed. Run: pip install cdsapi")


def download_era5_pv_pressure(year, month, day, pressure_levels=None,
                               outdir="", hours=None):
    """
    Download ERA5 PV on pressure levels.
    Useful if isentropic levels are not available or if you want
    to interpolate to theta levels yourself.
    Currently, no hourly ERA5 PV on isentropic levels available

    Parameters
    ----------
    year, month, day : int
    pressure_levels : list of int, optional
        Pressure levels in hPa. Default: stratospheric levels.
    outdir : str
    hours : list of str, optional
    """
    if not HAS_CDSAPI:
        raise RuntimeError("cdsapi not installed. Run: pip install cdsapi")

    os.makedirs(outdir, exist_ok=True)

    if hours is None:
        hours = [f"{h:02d}:00" for h in range(24)]

    if pressure_levels is None:
        pressure_levels = [
            1, 2, 3, 5, 7, 10, 20, 30, 50, 70, 100,
            125, 150, 175, 200, 225, 250, 300, 350, 
            #400, 450, 500, 550, 600, 650, 700, 750, 775, 
            #800, 825, 850, 875, 900, 926, 950, 975, 1000
        ]

    filename = (f"era5_pv_pressure_{year:04d}{month:02d}{day:02d}.nc")
    filepath = os.path.join(outdir, filename)

    if not os.path.exists(filepath):
        print(f"Downloading ERA5 PV (pressure levels) for {year}-{month:02d}-{day:02d}")
        print(f"  Levels: {pressure_levels} hPa")

        c = cdsapi.Client()

        c.retrieve(
            "reanalysis-era5-pressure-levels",
            {
                "product_type": "reanalysis",
                "variable": [
                    "potential_vorticity",
                    "temperature"
                    ],
                "pressure_level": [str(p) for p in pressure_levels],
                "year": str(year),
                "month": f"{month:02d}",
                "day": f"{day:02d}",
                "time": hours,
                "grid": ["0.25", "0.25"],
                #"grid": ["1.0", "1.0"],
                "format": "netcdf",
            },
            filepath,
        )

        print(f"  Done: {filepath}")
    
    else:
        print(f"ERA5 PV (pressure levels) for {year}-{month:02d}-{day:02d} already exists.")

    return filepath


# ---------------------------------------------------------------------------
#  Download for an explicit list of dates (e.g. GPS-ozonesonde manifest)
# ---------------------------------------------------------------------------

def download_era5_for_dates(dates, outdir, pressure_levels=None, hours=None):
    """
    Download ERA5 PV on pressure levels for an explicit list of dates.

    Parameters
    ----------
    dates : list of datetime.date | (year, month, day) tuples
    outdir : str
    pressure_levels : list of int, optional
    hours : list of str, optional

    Returns
    -------
    list of str : filepaths of the downloaded (or already-existing) files.
    """
    os.makedirs(outdir, exist_ok=True)

    filepaths = []
    for d in dates:
        year, month, day = d if isinstance(d, tuple) else (d.year, d.month, d.day)
        try:
            fp = download_era5_pv_pressure(
                year, month, day,
                pressure_levels=pressure_levels,
                outdir=outdir,
                hours=hours,
            )
            filepaths.append(fp)
        except Exception as e:
            print(f"  ERROR {year}-{month:02d}-{day:02d}: {e}")

    return filepaths


def _read_dates_file(path):
    """
    Read a list of dates from a manifest file.

    Accepts either a CSV with a 'date' column (e.g. the GPS-ozonesonde
    manifest written by download_ozonesondes.py) or a plain text file with
    one YYYY-MM-DD date per line.

    Returns
    -------
    list of datetime.date
    """
    import csv
    from datetime import datetime as _dt

    date_strs = []
    if path.lower().endswith('.csv'):
        with open(path, newline='') as fh:
            reader = csv.DictReader(fh)
            col = 'date' if (reader.fieldnames and 'date' in reader.fieldnames) \
                else (reader.fieldnames[0] if reader.fieldnames else None)
            if col is not None:
                date_strs = [row[col] for row in reader]
    else:
        with open(path) as fh:
            date_strs = [line.strip() for line in fh if line.strip()]

    return [_dt.strptime(s, "%Y-%m-%d").date() for s in date_strs]


# ---------------------------------------------------------------------------
#  CLI entry point
# ---------------------------------------------------------------------------
def main():
    """Download ERA5 PV for every day in a given year, or for a list of dates."""
    import calendar

    parser = argparse.ArgumentParser(
        description="Download ERA5 PV on pressure levels for a full year, "
                     "or for a specific list of dates via --dates-file."
    )
    parser.add_argument(
        "year", type=int, nargs="?", default=None,
        help="Year to download, e.g. 2023 (omit when using --dates-file)"
    )
    parser.add_argument(
        "--dates-file", type=str, default=None,
        help="CSV with a 'date' column, or a text file with one YYYY-MM-DD "
             "date per line (e.g. a GPS-ozonesonde manifest). "
             "Downloads only these dates instead of a full year."
    )
    parser.add_argument(
        "--outdir", type=str,
        default=os.environ.get("DATA", ".") + "/ERA5_12UTC",
        help="Output directory (default: $DATA/ERA5_12UTC)"
    )
    parser.add_argument(
        "--hours", nargs="+",
        default=[f"{h:02d}:00" for h in range(24)],
        help="UTC hours to download (default: all 24 hours)"
    )
    args = parser.parse_args()

    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    if args.dates_file:
        dates = _read_dates_file(args.dates_file)
        print(f"=== ERA5 download for {len(dates)} dates from {args.dates_file} ===")
        print(f"    Output directory: {outdir}")
        print(f"    Hours: {args.hours}")

        download_era5_for_dates(dates, outdir, hours=args.hours)

        print(f"=== Finished ERA5 download for {len(dates)} dates ===")
        return

    if args.year is None:
        parser.error("Either 'year' or --dates-file must be given.")

    year = args.year
    print(f"=== ERA5 download for year {year} ===")
    print(f"    Output directory: {outdir}")
    print(f"    Hours: {args.hours}")

    for month in range(1, 13):
        ndays = calendar.monthrange(year, month)[1]
        for day in range(1, ndays + 1):
            try:
                download_era5_pv_pressure(
                    year, month, day,
                    outdir=outdir,
                    hours=args.hours,
                )
            except Exception as e:
                print(f"  ERROR {year}-{month:02d}-{day:02d}: {e}")

    print(f"=== Finished ERA5 download for {year} ===")


if __name__ == "__main__":
    main()
    