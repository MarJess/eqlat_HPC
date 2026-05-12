"""
Batch processing of equivalent latitude over all time steps and
isentropic surfaces in a NetCDF file.

Two workflows
─────────────
1. ``process_netcdf``  –  PV is **already on isentropic levels**
   (ERA5 with levtype='pt', or a MERRA-2 file already interpolated)

   Typical layout:
       dims  : time, level [K], latitude, longitude
       var   : pv  (ERA5)  or  EPV  (MERRA-2 post-interpolation)

2. ``process_pressure_netcdf``  –  PV + T are on **pressure levels**;
   the function interpolates to each requested theta surface first.
   (MERRA-2 M2I3NPASM or ERA5 pressure-level download)

   Typical layout:
       dims  : time, level [hPa], latitude, longitude
       vars  : pv / EPV   (Ertel PV)
               T / t / ta (temperature, same pressure grid)

   Required extra argument:
       theta_levels : list[float]  – isentropic surfaces to compute [K]
                      e.g. [320, 340, 350, 360, 380, 400, 500, 600, 700, 800]

Both functions return an xarray.Dataset with variable ``eqlat``
of shape (time, theta, lat, lon).

"""

from __future__ import annotations

import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

try:
    import xarray as xr
    _HAS_XR = True
except ImportError:
    _HAS_XR = False

try:
    from tqdm import tqdm as _tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False

from .roi_fast       import eqlat_field_roi
from .piecewise      import eqlat_field_piecewise
from .interpolation  import interpolate_to_theta_vectorized


# ═══════════════════════════════════════════════════════════════
#  Common name candidates for auto-detection
# ═══════════════════════════════════════════════════════════════

_TIME_NAMES  = ("time", "valid_time")
_THETA_NAMES = ("level", "theta", "lev", "plev", "isentropic_level",
                "potential_temperature")
_PLEV_NAMES  = ("level", "lev", "plev", "pressure", "pressure_level",
                "isobaric", "hybrid")
_LAT_NAMES   = ("latitude", "lat", "nlat", "y")
_LON_NAMES   = ("longitude", "lon", "nlon", "x")
_PV_NAMES    = ("pv", "epv", "EPV", "PV", "ertel_pv", "q")
_T_NAMES     = ("T", "t", "temperature", "temp", "ta", "air_temperature",
                "TEMP", "Temperature")


# ═══════════════════════════════════════════════════════════════
#  Dimension / variable name helpers
# ═══════════════════════════════════════════════════════════════

def _find_dim(ds, candidates: tuple[str, ...], label: str,
              override: str | None = None) -> str:
    if override:
        return override
    for name in candidates:
        if name in ds.dims:
            return name
    raise KeyError(
        f"Could not auto-detect the '{label}' dimension. "
        f"Tried: {candidates}. "
        f"Set it explicitly via the '{label}_dim' keyword."
    )


def _find_var(ds, candidates: tuple[str, ...], label: str,
              override: str | None = None) -> str:
    if override:
        return override
    for name in candidates:
        if name in ds:
            return name
    raise KeyError(
        f"Could not auto-detect the '{label}' variable. "
        f"Tried: {candidates}. "
        f"Set it explicitly via the '{label}_var' keyword."
    )


# ═══════════════════════════════════════════════════════════════
#  Progress bar helpers
# ═══════════════════════════════════════════════════════════════

def _make_progress(total: int, desc: str, enabled: bool):
    """Return (_update, _close) callables."""
    if not enabled:
        return lambda: None, lambda: None

    if _HAS_TQDM:
        pbar = _tqdm(total=total, desc=desc, unit="slice")
        return pbar.update, pbar.close

    counter = [0]
    step = max(1, total // 20)

    def _update():
        counter[0] += 1
        if counter[0] % step == 0 or counter[0] == total:
            print(f"  {counter[0]}/{total}  ({100*counter[0]//total}%)")

    return _update, lambda: None


# ═══════════════════════════════════════════════════════════════
#  Low-level worker (also used as process target for n_workers > 1)
# ═══════════════════════════════════════════════════════════════

def _compute_one(args):
    """
    Compute the eqlat field for a single 2-D PV slice.

    args = (pv_slice, lat, lon, method, n_thresholds)
    """
    pv_slice, lat, lon, method, n_thresholds = args
    if method == "roi":
        return eqlat_field_roi(pv_slice, lat, lon,
                               n_thresholds=n_thresholds)
    return eqlat_field_piecewise(pv_slice, lat, lon,
                                 n_thresholds=n_thresholds)


def _run_slices(args_list: list, index_map: list,
                eqlat_out: np.ndarray, n_workers: int,
                _update, label: str):
    """Dispatch args_list either sequentially or in parallel."""
    if n_workers > 1:
        with ProcessPoolExecutor(max_workers=n_workers) as exe:
            fut_to_k = {exe.submit(_compute_one, a): k
                        for k, a in enumerate(args_list)}
            for fut in as_completed(fut_to_k):
                k = fut_to_k[fut]
                ti, θi = index_map[k]
                try:
                    eqlat_out[ti, θi] = fut.result()
                except Exception as exc:
                    warnings.warn(
                        f"{label} slice (t={ti}, θ={θi}) failed: {exc}",
                        RuntimeWarning, stacklevel=3,
                    )
                _update()
    else:
        for k, args in enumerate(args_list):
            ti, θi = index_map[k]
            try:
                eqlat_out[ti, θi] = _compute_one(args)
            except Exception as exc:
                warnings.warn(
                    f"{label} slice (t={ti}, θ={θi}) failed: {exc}",
                    RuntimeWarning, stacklevel=3,
                )
            _update()


def _build_dataset(eqlat_out, times, thetas,
                   t_dim, θ_dim, y_dim, x_dim,
                   lat, lon, method, n_thresholds, path, pv_name):
    """Wrap the numpy output array in an xarray.Dataset."""
    return xr.Dataset(
        {
            "eqlat": xr.DataArray(
                eqlat_out,
                dims=[t_dim, θ_dim, y_dim, x_dim],
                coords={
                    t_dim: times,
                    θ_dim: thetas,
                    y_dim: lat,
                    x_dim: lon,
                },
                attrs={
                    "long_name":      "Equivalent latitude",
                    "units":          "degrees_north",
                    "method":         method,
                    "n_thresholds":   n_thresholds,
                    "source_file":    str(path),
                    "source_pv_var":  pv_name,
                },
            )
        }
    )


# ═══════════════════════════════════════════════════════════════
#  Workflow 1 – PV already on isentropic levels
# ═══════════════════════════════════════════════════════════════

def process_netcdf(
    path: str,
    *,
    pv_var:    str | None = None,
    time_dim:  str | None = None,
    theta_dim: str | None = None,
    lat_dim:   str | None = None,
    lon_dim:   str | None = None,
    method:        str  = "roi",
    n_thresholds:  int  = 200,
    n_workers:     int  = 1,
    progress:      bool = True,
    time_slice:    slice | None = None,
    theta_slice:   slice | None = None,
) -> "xr.Dataset":
    """
    Compute equivalent latitude for every time step and isentropic
    level in a NetCDF file where PV is **already on isentropic levels**.

    Parameters
    ----------
    path : str
        Path to NetCDF.  Must contain PV on isentropic (theta) levels.

    pv_var : str, optional
        PV variable name (auto-detected from common names).

    time_dim, theta_dim, lat_dim, lon_dim : str, optional
        Dimension names (auto-detected).

    method : {"roi", "piecewise"}
        Equivalent-latitude algorithm.

    n_thresholds : int
        PV lookup-table resolution (higher = more accurate, slower).

    n_workers : int
        Parallel worker processes (1 = sequential, safest).

    progress : bool
        Show progress bar / printout.

    time_slice, theta_slice : slice, optional
        Process a subset only, e.g. ``time_slice=slice(0, 5)``.

    Returns
    -------
    xr.Dataset
        Variable ``eqlat``  shape (time, theta, lat, lon)  [°N].

    Examples
    --------
    >>> ds = process_netcdf("era5_pv_isentropic.nc", method="roi")
    >>> ds["eqlat"].sel(level=350).isel(time=0).plot()
    """
    if not _HAS_XR:
        raise ImportError("xarray is required: pip install xarray")

    ds = xr.open_dataset(path, decode_times=True)

    t_dim = _find_dim(ds, _TIME_NAMES,  "time",       time_dim)
    θ_dim = _find_dim(ds, _THETA_NAMES, "theta/level", theta_dim)
    y_dim = _find_dim(ds, _LAT_NAMES,   "lat",         lat_dim)
    x_dim = _find_dim(ds, _LON_NAMES,   "lon",         lon_dim)
    pv    = _find_var(ds, _PV_NAMES,    "PV",          pv_var)

    da = ds[pv]
    if time_slice  is not None: da = da.isel({t_dim: time_slice})
    if theta_slice is not None: da = da.isel({θ_dim: theta_slice})

    lat    = da[y_dim].values.astype(np.float64)
    lon    = da[x_dim].values.astype(np.float64)
    times  = da[t_dim].values
    thetas = da[θ_dim].values

    n_time, n_theta = len(times), len(thetas)
    n_lat,  n_lon   = len(lat),   len(lon)
    total = n_time * n_theta

    eqlat_out = np.full((n_time, n_theta, n_lat, n_lon), np.nan,
                        dtype=np.float32)

    _update, _close = _make_progress(total, f"eqlat/{method}", progress)

    args_list, index_map = [], []
    for ti in range(n_time):
        for θi in range(n_theta):
            pv_slice = da.isel({t_dim: ti, θ_dim: θi}).values
            args_list.append((pv_slice, lat, lon, method, n_thresholds))
            index_map.append((ti, θi))

    _run_slices(args_list, index_map, eqlat_out, n_workers,
                _update, "process_netcdf")
    _close()

    result = _build_dataset(eqlat_out, times, thetas,
                            t_dim, θ_dim, y_dim, x_dim,
                            lat, lon, method, n_thresholds, path, pv)
    ds.close()
    return result


# ═══════════════════════════════════════════════════════════════
#  Workflow 2 – PV + T on pressure levels → interpolate first
# ═══════════════════════════════════════════════════════════════

def process_pressure_netcdf(
    path: str,
    theta_levels: list[float],
    *,
    # variable overrides
    pv_var:   str | None = None,
    t_var:    str | None = None,
    # dimension overrides
    time_dim: str | None = None,
    plev_dim: str | None = None,
    lat_dim:  str | None = None,
    lon_dim:  str | None = None,
    # pressure coordinate
    p0:    float = 1000.0,   # reference pressure [hPa]
    kappa: float = 0.286,    # R/cp
    # method options
    method:       str  = "roi",
    n_thresholds: int  = 200,
    # performance
    n_workers: int  = 1,
    progress:  bool = True,
    # subset
    time_slice: slice | None = None,
) -> "xr.Dataset":
    """
    Interpolate PV from pressure levels to isentropic surfaces and
    then compute equivalent latitude for every time step and theta level.

    Use this for MERRA-2 (M2I3NPASM) or ERA5 pressure-level downloads
    that contain both the PV field and temperature on the same pressure grid.

    Parameters
    ----------
    path : str
        NetCDF file with PV and T on pressure levels.

    theta_levels : list of float
        Isentropic surfaces to compute [K].
        Example: [320, 340, 350, 360, 380, 400, 500, 600, 700, 800]

    pv_var : str, optional
        Name of the PV variable (auto-detected from common names:
        'pv', 'EPV', 'epv', 'PV', 'ertel_pv', 'q').

    t_var : str, optional
        Name of the temperature variable (auto-detected from:
        'T', 't', 'temperature', 'temp', 'ta', 'air_temperature').

    time_dim, plev_dim, lat_dim, lon_dim : str, optional
        Dimension names (auto-detected).

    p0 : float
        Reference pressure for potential temperature [hPa] (default 1000).

    kappa : float
        R/cp ratio (default 0.286 for dry air).

    method : {"roi", "piecewise"}
        Equivalent-latitude algorithm.

    n_thresholds : int
        PV lookup-table resolution.

    n_workers : int
        Parallel worker processes (1 = sequential).

    progress : bool
        Show progress bar / printout.

    time_slice : slice, optional
        Process only a time subset, e.g. ``slice(0, 10)``.

    Returns
    -------
    xr.Dataset
        Variable ``eqlat``  shape (time, theta, lat, lon)  [°N].
        Also contains ``pv_isentropic`` shape (time, theta, lat, lon)
        with the interpolated PV values [PVU] for diagnostics.

    Notes
    -----
    The pressure coordinate values are read from the file and must be
    in hPa.  MERRA-2 uses hPa by default; ERA5 pressure-level files
    use hPa as well.  If your file stores pressure in Pa, pass the
    appropriate conversion (e.g. divide the coordinate by 100 before
    calling this function, or override with ``plev_dim``).

    The interpolation uses ``interpolate_to_theta_vectorized`` from
    ``eqlat.interpolation``, which is vectorized over all (lat, lon)
    columns simultaneously.

    Examples
    --------
    # MERRA-2 pressure-level file
    >>> ds = process_pressure_netcdf(
    ...     "MERRA2_400.inst3_3d_asm_Np.20050101.nc4",
    ...     theta_levels=[320, 350, 380, 400, 500, 600, 700, 800],
    ...     method="roi",
    ...     n_thresholds=200,
    ...     progress=True,
    ... )
    >>> ds["eqlat"].sel(theta=380).isel(time=0).plot()
    >>> ds["pv_isentropic"].sel(theta=380).isel(time=0).plot()

    # ERA5 pressure-level file
    >>> ds = process_pressure_netcdf(
    ...     "era5_pressure_levels.nc",
    ...     theta_levels=[340, 360, 380, 400],
    ...     pv_var="pv",
    ...     t_var="t",
    ...     method="roi",
    ... )
    """
    if not _HAS_XR:
        raise ImportError("xarray is required: pip install xarray")

    theta_levels = sorted(float(θ) for θ in theta_levels)
    n_theta = len(theta_levels)

    # ── open dataset ───────────────────────────────────────────
    ds = xr.open_dataset(path, decode_times=True)

    # ── resolve names ──────────────────────────────────────────
    t_dim  = _find_dim(ds, _TIME_NAMES, "time",    time_dim)
    p_dim  = _find_dim(ds, _PLEV_NAMES, "plev",    plev_dim)
    y_dim  = _find_dim(ds, _LAT_NAMES,  "lat",     lat_dim)
    x_dim  = _find_dim(ds, _LON_NAMES,  "lon",     lon_dim)
    pv_name = _find_var(ds, _PV_NAMES,  "PV",      pv_var)
    t_name  = _find_var(ds, _T_NAMES,   "temperature", t_var)

    # ── read coordinate arrays ─────────────────────────────────
    da_pv = ds[pv_name]
    da_T  = ds[t_name]

    if time_slice is not None:
        da_pv = da_pv.isel({t_dim: time_slice})
        da_T  = da_T.isel({t_dim: time_slice})

    lat      = da_pv[y_dim].values.astype(np.float64)
    lon      = da_pv[x_dim].values.astype(np.float64)
    times    = da_pv[t_dim].values
    p_levels = da_pv[p_dim].values.astype(np.float64)   # [hPa]

    n_time = len(times)
    n_lat  = len(lat)
    n_lon  = len(lon)
    total  = n_time * n_theta

    print(f"Pressure levels in file: {p_levels.min():.1f}–{p_levels.max():.1f} hPa  ({len(p_levels)} levels)")
    print(f"Theta levels requested:  {theta_levels}")
    print(f"Grid: {n_lat} lat × {n_lon} lon,  {n_time} time steps")
    print(f"Total slices: {n_time} × {n_theta} = {total}")

    # ── allocate outputs ───────────────────────────────────────
    eqlat_out = np.full((n_time, n_theta, n_lat, n_lon), np.nan,
                        dtype=np.float32)
    pv_iso_out = np.full_like(eqlat_out, np.nan)

    # ── progress bar ───────────────────────────────────────────
    _update, _close = _make_progress(
        total, f"interp+eqlat/{method}", progress
    )

    # ── main loop – iterate time first, then theta ─────────────
    # Loading one time step at a time keeps memory usage bounded.
    for ti in range(n_time):

        # Load 3-D block for this time step: (nlev, nlat, nlon)
        # da_pv has dims (time, level, lat, lon) or (time, lat, level, lon) etc.
        # We re-order to (level, lat, lon) for interpolate_to_theta_vectorized.
        pv_3d = (da_pv.isel({t_dim: ti})
                      .transpose(p_dim, y_dim, x_dim)
                      .values.astype(np.float64))
        T_3d  = (da_T.isel({t_dim: ti})
                     .transpose(p_dim, y_dim, x_dim)
                     .values.astype(np.float64))

        for θi, theta_val in enumerate(theta_levels):

            # ── Step 1: interpolate PV to this theta surface ───
            try:
                pv_iso = interpolate_to_theta_vectorized(
                    pv_3d, T_3d, p_levels, theta_val,
                    p0=p0, kappa=kappa,
                )                                # shape (nlat, nlon)
            except Exception as exc:
                warnings.warn(
                    f"Interpolation failed (t={ti}, θ={theta_val} K): {exc}",
                    RuntimeWarning, stacklevel=2,
                )
                _update()
                continue

            pv_iso_out[ti, θi] = pv_iso.astype(np.float32)

            # ── Step 2: compute eqlat on the isentropic slice ──
            try:
                eqlat_out[ti, θi] = _compute_one(
                    (pv_iso, lat, lon, method, n_thresholds)
                )
            except Exception as exc:
                warnings.warn(
                    f"eqlat failed (t={ti}, θ={theta_val} K): {exc}",
                    RuntimeWarning, stacklevel=2,
                )

            _update()

    _close()

    # ── build output Dataset ───────────────────────────────────
    theta_arr = np.array(theta_levels, dtype=np.float64)
    theta_dim_name = "theta"     # always named 'theta' in output

    result = xr.Dataset(
        {
            "eqlat": xr.DataArray(
                eqlat_out,
                dims=[t_dim, theta_dim_name, y_dim, x_dim],
                coords={
                    t_dim:          times,
                    theta_dim_name: theta_arr,
                    y_dim:          lat,
                    x_dim:          lon,
                },
                attrs={
                    "long_name":    "Equivalent latitude",
                    "units":        "degrees_north",
                    "method":       method,
                    "n_thresholds": n_thresholds,
                    "source_file":  str(path),
                    "source_pv":    pv_name,
                    "source_T":     t_name,
                },
            ),
            "pv_isentropic": xr.DataArray(
                pv_iso_out,
                dims=[t_dim, theta_dim_name, y_dim, x_dim],
                coords={
                    t_dim:          times,
                    theta_dim_name: theta_arr,
                    y_dim:          lat,
                    x_dim:          lon,
                },
                attrs={
                    "long_name": "Ertel PV on isentropic surface",
                    "units":     "PVU",
                },
            ),
        }
    )

    ds.close()
    return result


# ═══════════════════════════════════════════════════════════════
#  Convenience wrappers
# ═══════════════════════════════════════════════════════════════

def process_netcdf_piecewise(path: str, **kwargs) -> "xr.Dataset":
    """Shortcut: process_netcdf with method='piecewise'."""
    kwargs.setdefault("method", "piecewise")
    return process_netcdf(path, **kwargs)


def process_netcdf_roi(path: str, **kwargs) -> "xr.Dataset":
    """Shortcut: process_netcdf with method='roi'."""
    kwargs.setdefault("method", "roi")
    return process_netcdf(path, **kwargs)


def process_pressure_netcdf_roi(path: str, theta_levels: list[float],
                                 **kwargs) -> "xr.Dataset":
    """Shortcut: process_pressure_netcdf with method='roi'."""
    kwargs.setdefault("method", "roi")
    return process_pressure_netcdf(path, theta_levels, **kwargs)


def process_pressure_netcdf_piecewise(path: str, theta_levels: list[float],
                                       **kwargs) -> "xr.Dataset":
    """Shortcut: process_pressure_netcdf with method='piecewise'."""
    kwargs.setdefault("method", "piecewise")
    return process_pressure_netcdf(path, theta_levels, **kwargs)
