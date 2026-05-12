"""
Swoosh zonal mean method for equivalent latitude computation.

Swoosh has Ozone as a zonal mean in latitude and potential temperature coordinates. 
Ozon changes monotonically (in the stratosphere) from tropics to pole. 

Works for single hemisphere only because monotonic change of Ozone on isentrop is needed
"""

import numpy as np
import xarray as xr 
from scipy.interpolate import interp1d


def equivalent_latitude_swoosh(
        swoosh_ds : xr.Dataset,
        sonde_theta : np.ndarray,
        sonde_o3 : np.ndarray,
        sonde_time : np.datetime64,
        o3_varname : str = "combinedo3q",
        lat_dim : str = 'lat',
        theta_dim : str = 'level',
        time_dim : str = 'time',
        monotone_enforce : bool = True,
        monotone_tolerance : float = 0.0
):
    """
    Calculate equivalent latitude for an ozonesonde profile using SWOOSH zonal means.

    Maps ozonesonde mixing ratios to latitudes by treating ozone as a coordinate 
    on isentropic surfaces. The function interpolates the SWOOSH zonal mean 
    climatology to the sonde's time and potential temperature levels, then 
    inverts the Ozone-Latitude relationship to find the 'equivalent' latitude.

    Parameters
    ----------
    swoosh_ds : xr.Dataset
        The SWOOSH dataset containing zonal mean ozone (usually 3D: time, lat, level).
    sonde_theta : np.ndarray
        Potential temperature levels of the ozonesonde [K].
    sonde_o3 : np.ndarray
        Ozone mixing ratios from the sonde [e.g., ppmv or mixing ratio]. 
        Must match units in `swoosh_ds`.
    sonde_time : np.datetime64
        The valid time of the ozonesonde launch for temporal interpolation.
    o3_varname : str, optional
        The variable name for ozone in `swoosh_ds`. Default is "combinedo3q".
    lat_dim : str, optional
        Name of the latitude dimension. Default is 'lat'.
    theta_dim : str, optional
        Name of the vertical (isentropic) dimension. Default is 'level'.
    time_dim : str, optional
        Name of the time dimension. Default is 'time'.
    monotone_enforce : bool, optional
        If True, forces the reference ozone profile to be monotonic using 
        accumulation. Helps handle noisy zonal means. Default is True.
    monotone_tolerance : float, optional
        Allowed deviation from monotonicity before a level is rejected. 
        Only used if `monotone_enforce` is True. Default is 0.0.

    Returns
    -------
    eqlat : np.ndarray
        Array of equivalent latitudes [degrees_north] corresponding to 
        `sonde_theta`. Contains NaNs where interpolation is not possible.
    o3_ref : xr.DataArray
        The 1D zonal mean ozone profile (Lat) interpolated to `sonde_time`.
    """

    o3_zm = swoosh_ds[o3_varname]

    # time interpolation (linear in between monthly means)
    o3_ref = o3_zm.interp(
        {time_dim: sonde_time},
        method='linear', 
        kwargs={'fill_value': 'extrapolate'}
    )

    lats = o3_ref[lat_dim].values
    thetas = o3_ref[theta_dim].values 

    # only NH for now 
    nh_mask = lats >=0 
    lats_nh = lats[nh_mask]
    o3_ref_nh = o3_ref.isel({lat_dim : nh_mask})

    # create empty storage for equivalent latitude
    eqlat = np.full(len(sonde_theta), np.nan)

    for i, (th, o3_val) in enumerate(zip(sonde_theta, sonde_o3)):

        # Theta interpolation in SWOOOSH 
        if th < thetas.min() or th > thetas.max():
            continue

        o3_profile = o3_ref_nh.interp(
            {theta_dim: th}, method='linear'
        ).values

        valid = np.isfinite(o3_profile)
        if valid.sum() < 3:
            continue

        lats_v = lats_nh[valid]
        o3_v = o3_profile[valid]

        increasing = o3_v[-1] >= o3_v[0]

        if monotone_enforce:
            if increasing:
                o3_accumulated = np.maximum.accumulate(o3_v)
                if monotone_tolerance > 0.0:
                    max_deviation = np.max(o3_accumulated - o3_v)
                    if max_deviation > monotone_tolerance:
                        continue  # echte Nicht-Monotonie → NaN
            else:
                o3_accumulated = np.minimum.accumulate(o3_v)
                if monotone_tolerance > 0.0:
                    max_deviation = np.max(o3_v - o3_accumulated)
                    if max_deviation > monotone_tolerance:
                        continue  # echte Nicht-Monotonie → NaN
            o3_v = o3_accumulated
        else:
            if not (np.all(np.diff(o3_v) >= 0) or np.all(np.diff(o3_v) <= 0)):
                continue  # weder steigend noch fallend → NaN

        if o3_val < o3_v.min() or o3_val > o3_v.max():
            continue

        # interpolation of O3 value to latitude
        if not increasing:
            f = interp1d(o3_v[::-1], lats_v[::-1], kind="linear")
        else:
            f = interp1d(o3_v, lats_v, kind="linear")

        eqlat[i] = f(o3_val)
    
    return eqlat, o3_ref


def equivalent_latitude_swoosh_new(
        swoosh_ds: xr.Dataset,
        sonde_theta: np.ndarray,
        sonde_o3: np.ndarray,
        sonde_time: np.datetime64,
        o3_varname: str = "combinedo3q",
        lat_dim: str = 'lat',
        theta_dim: str = 'level',
        time_dim: str = 'time',
        monotone_enforce: bool = True,
        monotone_tolerance: float = 0.0
):
    """
    Calculate Equivalent Latitude (EqL) for ozone sonde profiles using SWOOSH as a reference.

    This function maps ozone mixing ratios from a vertical profile (sonde) to the 
    latitudinal position where that same mixing ratio exists in the zonal mean 
    climatology (SWOOSH) at the same potential temperature (theta) and time.

    Parameters
    ----------
    swoosh_ds : xr.Dataset
        The SWOOSH dataset containing zonal mean ozone. Must include latitude, 
        potential temperature (level), and time dimensions.
    sonde_theta : np.ndarray
        Potential temperature levels of the sonde profile [K].
    sonde_o3 : np.ndarray
        Ozone mixing ratios of the sonde profile [ppmv or equivalent to SWOOSH].
    sonde_time : np.datetime64
        The timestamp of the sonde launch used for temporal interpolation of SWOOSH.
    o3_varname : str, optional
        The variable name for ozone in `swoosh_ds`. Default is "combinedo3q".
    lat_dim : str, optional
        Name of the latitude dimension. Default is 'lat'.
    theta_dim : str, optional
        Name of the vertical/potential temperature dimension. Default is 'level'.
    time_dim : str, optional
        Name of the time dimension. Default is 'time'.
    monotone_enforce : bool, optional
        If True, forces the reference ozone profile to be monotonic before 
        interpolation. This prevents ambiguous mapping in regions with low 
        gradients or noise. Default is True.
    monotone_tolerance : float, optional
        Maximum allowed non-monotonic deviation. If the profile deviates by 
        more than this value, the result for that level is NaN. Default is 0.0.

    Returns
    -------
    eqlat : np.ndarray
        Array of equivalent latitudes corresponding to each level in `sonde_theta`.
    o3_ref_plot : xr.DataArray
        The time-interpolated 2D (lat vs. level) SWOOSH ozone field used for 
        the calculation, useful for validation plotting.

    Notes
    -----
    The calculation assumes that ozone is a valid proxy for potential vorticity (PV) 
    in the stratosphere. It performs a linear interpolation in time and theta space 
    first, then solves for latitude level-by-level.
    """
    # Slice time and NH immediately to reduce memory footprint
    o3_zm = swoosh_ds[o3_varname].sel({lat_dim: slice(0, 90)})

    # time interpolation (linear in between monthly means)
    o3_ref_plot = o3_zm.interp(
        {time_dim: sonde_time},
        method='linear', 
        kwargs={'fill_value': 'extrapolate'}
    )
    
    # Interpolate SWOOSH to the sonde's time and ALL sonde theta levels at once
    # This replaces the theta interpolation inside the loop
    o3_ref = o3_ref_plot.interp(
        {theta_dim: sonde_theta},
        method='linear', 
        kwargs={'fill_value': 'extrapolate'}
    )

    lats_nh = o3_ref[lat_dim].values
    eqlat = np.full(len(sonde_theta), np.nan)

    # Loop only for the O3 -> Lat mapping (the non-linear part)
    # We use .values to avoid xarray overhead inside the loop
    o3_ref_values = o3_ref.values # Shape: (sonde_theta, lats)
    
    for i in range(len(sonde_theta)):
        o3_profile = o3_ref_values[i, :]
        o3_val = sonde_o3[i]

        # Filter NaNs
        mask = np.isfinite(o3_profile)
        if mask.sum() < 2:
            continue
            
        o3_v = o3_profile[mask]
        lats_v = lats_nh[mask]

        increasing = o3_v[-1] >= o3_v[0]

        if monotone_enforce:
            if increasing:
                o3_accumulated = np.maximum.accumulate(o3_v)
                if monotone_tolerance > 0.0:
                    max_deviation = np.max(o3_accumulated - o3_v)
                    if max_deviation > monotone_tolerance:
                        continue  # echte Nicht-Monotonie → NaN
            else:
                o3_accumulated = np.minimum.accumulate(o3_v)
                if monotone_tolerance > 0.0:
                    max_deviation = np.max(o3_v - o3_accumulated)
                    if max_deviation > monotone_tolerance:
                        continue  # echte Nicht-Monotonie → NaN
            o3_v = o3_accumulated
        else:
            if not (np.all(np.diff(o3_v) >= 0) or np.all(np.diff(o3_v) <= 0)):
                continue  # weder steigend noch fallend → NaN

        # Range check
        if o3_val < o3_v.min() or o3_val > o3_v.max():
            continue

        # Interpolate O3 value to Latitude (handles both directions)
        if not increasing:
            eqlat[i] = np.interp(o3_val, o3_v[::-1], lats_v[::-1])
        else:
            eqlat[i] = np.interp(o3_val, o3_v, lats_v)
    
    return eqlat, o3_ref_plot