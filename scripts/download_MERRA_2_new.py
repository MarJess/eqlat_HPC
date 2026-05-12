"""
Download MERRA-2 data from NASA GES DISC for equivalent latitude computation.

Prerequisites:
    1. Register at https://urs.earthdata.nasa.gov/
    2. Link GES DISC to your Earthdata account:
       https://disc.gsfc.nasa.gov/earthdata-login
    3. Set up authentication:
       Create ~/.netrc with:
           machine urs.earthdata.nasa.gov
           login <your-username>
           password <your-password>
    4. pip install requests

MERRA-2 relevant collections:
    - M2I3NPASM (inst3_3d_asm_Np): 3-hourly instantaneous on pressure levels
      Contains: T, U, V, PV (EPV), etc. on 42 pressure levels
      Resolution: 0.5° x 0.625°
      Time steps per day: 8  (00, 03, 06, 09, 12, 15, 18, 21 UTC)
    - M2I6NPANA (inst6_3d_ana_Np): 6-hourly analyzed on pressure levels
      Time steps per day: 4  (00, 06, 12, 18 UTC)

OPeNDAP subsetting:
    Variables and dimensions can be subsetted directly in the URL, e.g.:
        .nc4?EPV[0:1:0][0:1:41][0:1:360][0:1:575]
             ^var  ^time ^lev   ^lat     ^lon
    This avoids downloading the full ~1 GB daily file.

Note: MERRA-2 does not directly provide PV on isentropic surfaces,
so we download T and PV on pressure levels and interpolate
to isentropic levels using the temperature field.
"""

import os
from datetime import datetime, timedelta

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ---------------------------------------------------------------------------
# Collection metadata
# ---------------------------------------------------------------------------

COLLECTION_INFO = {
    "M2I3NPASM": {
        "short":     "inst3_3d_asm_Np",
        "prefix_fn": lambda stream: f"MERRA2_{stream}.inst3_3d_asm_Np",
        "n_times":   8,           # 00,03,06,09,12,15,18,21 UTC
        "dt_hours":  3,
        "n_lev":     42,
        "n_lat":     361,
        "n_lon":     576,
        "server":    "goldsmr5",  # pressure-level server
    },
    "M2I6NPANA": {
        "short":     "inst6_3d_ana_Np",
        "prefix_fn": lambda stream: f"MERRA2_{stream}.inst6_3d_ana_Np",
        "n_times":   4,           # 00,06,12,18 UTC
        "dt_hours":  6,
        "n_lev":     42,
        "n_lat":     361,
        "n_lon":     576,
        "server":    "goldsmr5",
    },
}


def _stream_number(year, month, day):
    """Return the MERRA-2 stream number string for a given date."""
    date = datetime(year, month, day)
    if date < datetime(1992, 1, 1):
        return "100"
    elif date < datetime(2001, 1, 1):
        return "200"
    elif date < datetime(2011, 1, 1):
        return "300"
    else:
        return "400"


def hour_to_time_index(hour_utc, collection="M2I3NPASM"):
    """
    Convert a UTC hour to the corresponding time index in a MERRA-2 file.

    Parameters
    ----------
    hour_utc : int or float
        UTC hour (0–23). Will be rounded to the nearest valid time step.
    collection : str

    Returns
    -------
    time_index : int
    valid_hour  : int   (the actual UTC hour that index corresponds to)
    """
    dt_h = COLLECTION_INFO[collection]["dt_hours"]
    n_t  = COLLECTION_INFO[collection]["n_times"]
    idx  = round(hour_utc / dt_h) % n_t
    return idx, idx * dt_h


def get_merra2_opendap_url(year, month, day,
                            time_indices=None,
                            variables=None,
                            collection="M2I3NPASM",
                            version="5.12.4"):
    """
    Construct an OPeNDAP URL for a MERRA-2 file, optionally with
    dimension subsetting for time steps and variables.

    OPeNDAP index syntax:  VAR[t_start:1:t_end][lev][lat][lon]
    All spatial dimensions are kept at full resolution by default.

    Parameters
    ----------
    year, month, day : int
    time_indices : int | list[int] | None
        Which time indices to request (0-based).
        - None  → all time steps (no subsetting)
        - int   → single time step
        - list  → contiguous range [min, max] (OPeNDAP requires a range)
    variables : list[str] | None
        Variable names, e.g. ['EPV', 'T']. None → full file (no var subset).
    collection : str
    version : str

    Returns
    -------
    url : str
    filename : str   (local save name, without path)
    """
    info   = COLLECTION_INFO.get(collection)
    if info is None:
        raise ValueError(f"Unknown collection: {collection}. "
                         f"Choose from {list(COLLECTION_INFO)}")

    stream   = _stream_number(year, month, day)
    prefix   = info["prefix_fn"](stream)
    nc4_name = f"{prefix}.{year:04d}{month:02d}{day:02d}.nc4"

    base = (f"https://{info['server']}.gesdisc.eosdis.nasa.gov/opendap/"
            f"MERRA2/{collection}.{version}/"
            f"{year:04d}/{month:02d}/{nc4_name}")

    # ------------------------------------------------------------------ #
    # Build OPeNDAP constraint expression if subsetting is requested
    # ------------------------------------------------------------------ #
    if variables is None and time_indices is None:
        # No subsetting → plain .nc4 URL (full file download via HTTP)
        return base, nc4_name

    # Resolve time index range
    n_t = info["n_times"]
    if time_indices is None:
        t0, t1 = 0, n_t - 1
    elif isinstance(time_indices, (int, float)):
        t0 = t1 = int(time_indices)
    else:
        time_indices = list(time_indices)
        t0, t1 = min(time_indices), max(time_indices)

    if not (0 <= t0 <= t1 < n_t):
        raise ValueError(f"time_indices out of range for {collection} "
                         f"(0–{n_t-1}): got [{t0}, {t1}]")

    n_lev = info["n_lev"]
    n_lat = info["n_lat"]
    n_lon = info["n_lon"]

    # Dimension suffix applied to every variable
    dim_suffix = (f"[{t0}:1:{t1}]"
                  f"[0:1:{n_lev-1}]"
                  f"[0:1:{n_lat-1}]"
                  f"[0:1:{n_lon-1}]")

    # Coordinate variables (1-D, no lev/lat/lon dims where not applicable)
    coord_vars = {
        "time":  f"[{t0}:1:{t1}]",
        "lev":   f"[0:1:{n_lev-1}]",
        "lat":   f"[0:1:{n_lat-1}]",
        "lon":   f"[0:1:{n_lon-1}]",
    }

    if variables is None:
        variables = ["EPV", "T"]

    parts = []
    for cv, cdim in coord_vars.items():
        parts.append(f"{cv}{cdim}")
    for v in variables:
        parts.append(f"{v}{dim_suffix}")

    constraint = ",".join(parts)
    url = f"{base}.nc4?{constraint}"

    # Build a descriptive local filename
    if t0 == t1:
        t_str = f"t{t0:02d}"
    else:
        t_str = f"t{t0:02d}-{t1:02d}"
    var_str  = "_".join(variables)
    filename = f"merra2_{var_str}_{year:04d}{month:02d}{day:02d}_{t_str}.nc4"

    return url, filename


# ---------------------------------------------------------------------------
# Main download function
# ---------------------------------------------------------------------------

def download_merra2(year, month, day,
                    hours_utc=None,
                    variables=None,
                    collection="M2I3NPASM",
                    version="5.12.4",
                    outdir=".",
                    overwrite=False):
    """
    Download a time-subsetted MERRA-2 file via OPeNDAP.

    Parameters
    ----------
    year, month, day : int
    hours_utc : int | float | list | None
        UTC hour(s) to download.
        - None              → all time steps (full day)
        - single int/float  → nearest time step, e.g. 12 → index 4 for 3-h data
        - list of int/float → all steps covering the requested hours
          (the OPeNDAP request fetches the contiguous range [min_idx, max_idx])
    variables : list[str] | None
        E.g. ['EPV', 'T']. None defaults to ['EPV', 'T'].
    collection : str
    version : str
    outdir : str
    overwrite : bool

    Returns
    -------
    outfile : str   (path to saved file)

    Examples
    --------
    # Single time step at 12 UTC
    download_merra2(2019, 6, 15, hours_utc=12)

    # Multiple specific hours  (fetches contiguous range between them)
    download_merra2(2019, 6, 15, hours_utc=[0, 6, 12])

    # Full day
    download_merra2(2019, 6, 15, hours_utc=None)
    """
    if not HAS_REQUESTS:
        raise RuntimeError("'requests' not installed. Run: pip install requests")

    if variables is None:
        variables = ["EPV", "T"]

    # Resolve hours → time indices
    if hours_utc is None:
        time_indices = None
    else:
        if isinstance(hours_utc, (int, float)):
            hours_utc = [hours_utc]
        dt_h    = COLLECTION_INFO[collection]["dt_hours"]
        n_t     = COLLECTION_INFO[collection]["n_times"]
        indices = sorted({round(h / dt_h) % n_t for h in hours_utc})
        time_indices = indices if len(indices) > 1 else indices[0]

    url, filename = get_merra2_opendap_url(
        year, month, day,
        time_indices=time_indices,
        variables=variables,
        collection=collection,
        version=version,
    )

    os.makedirs(outdir, exist_ok=True)
    outfile = os.path.join(outdir, filename)

    if os.path.exists(outfile) and not overwrite:
        print(f"Already exists, skipping: {outfile}")
        return outfile

    print(f"Downloading MERRA-2  {year}-{month:02d}-{day:02d}")
    print(f"  Collection : {collection}")
    print(f"  Variables  : {variables}")
    if time_indices is None:
        print(f"  Time steps : all")
    else:
        idxs = ([time_indices] if isinstance(time_indices, int)
                else list(range(min(time_indices), max(time_indices)+1)))
        dt_h = COLLECTION_INFO[collection]["dt_hours"]
        hours = [i * dt_h for i in idxs]
        print(f"  Time steps : indices {idxs}  →  {hours} UTC")
    print(f"  URL        : {url}")
    print(f"  Output     : {outfile}")

    session  = requests.Session()   # ~/.netrc handles Earthdata auth
    response = session.get(url, stream=True)

    if response.status_code == 200:
        with open(outfile, "wb") as fh:
            for chunk in response.iter_content(chunk_size=8192):
                fh.write(chunk)
        size_mb = os.path.getsize(outfile) / 1e6
        print(f"  Done  ({size_mb:.1f} MB)")
    else:
        print(f"  Error: HTTP {response.status_code}")
        print(f"  {response.text[:500]}")

    return outfile


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def download_merra2_single_hour(year, month, day, hour_utc,
                                 variables=None, collection="M2I3NPASM",
                                 outdir=".", **kwargs):
    """Download the single MERRA-2 time step closest to `hour_utc`."""
    return download_merra2(year, month, day,
                           hours_utc=hour_utc,
                           variables=variables,
                           collection=collection,
                           outdir=outdir, **kwargs)


def download_merra2_date_range(start_date, end_date, hours_utc=None,
                                variables=None, collection="M2I3NPASM",
                                outdir=".", **kwargs):
    """
    Download MERRA-2 for every day in [start_date, end_date].

    Parameters
    ----------
    start_date, end_date : datetime or (year, month, day) tuple
    hours_utc : same as download_merra2
    """
    if isinstance(start_date, tuple):
        start_date = datetime(*start_date)
    if isinstance(end_date, tuple):
        end_date   = datetime(*end_date)

    outfiles = []
    current  = start_date
    while current <= end_date:
        f = download_merra2(current.year, current.month, current.day,
                            hours_utc=hours_utc,
                            variables=variables,
                            collection=collection,
                            outdir=outdir, **kwargs)
        outfiles.append(f)
        current += timedelta(days=1)
    return outfiles
