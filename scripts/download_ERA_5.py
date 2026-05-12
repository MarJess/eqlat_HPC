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
        hours = ["00:00"]

    if pressure_levels is None:
        pressure_levels = [
            1, 2, 3, 5, 7, 10, 20, 30, 50, 70, 100,
            125, 150, 175, 200, 225, 250, 300, 325, 350
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
    