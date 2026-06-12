"""
Interpolation utilities for converting PV from pressure levels
to isentropic (potential temperature) surfaces.

MERRA-2 and ERA5 provide PV on pressure levels, so interpolation to
theta surfaces is needed.
"""

import numpy as np


def potential_temperature(T, p, p0=1000.0, kappa=0.286):
    """
    Compute potential temperature.

    θ = T * (p₀/p)^κ

    Parameters
    ----------
    T : ndarray
        Temperature in K.
    p : float or ndarray
        Pressure in hPa.
    p0 : float
        Reference pressure in hPa (default: 1000 hPa).
    kappa : float
        R/cp (default: 0.286 for dry air).

    Returns
    -------
    theta : ndarray
        Potential temperature in K.
    """
    return T * (p0 / p) ** kappa


def interpolate_to_theta(field, T, p_levels, theta_target,
                          p0=1000.0, kappa=0.286, log_p=True):
    """
    Interpolate a 3D field from pressure levels to an isentropic surface.

    Parameters
    ----------
    field : ndarray, shape (nlev, nlat, nlon)
        The field to interpolate (e.g., PV).
    T : ndarray, shape (nlev, nlat, nlon)
        Temperature on pressure levels.
    p_levels : array_like, shape (nlev,)
        Pressure levels in hPa (must be monotonically decreasing,
        i.e., from surface to top of atmosphere).
    theta_target : float
        Target potential temperature level in K.
    p0 : float
        Reference pressure (default: 1000 hPa).
    kappa : float
        R/cp ratio.
    log_p : bool
        If True, interpolate in log-pressure space.

    Returns
    -------
    field_theta : ndarray, shape (nlat, nlon)
        Field interpolated to the theta_target surface.
    p_theta : ndarray, shape (nlat, nlon)
        Pressure of the theta surface at each grid point (hPa).
    """
    p_levels = np.asarray(p_levels, dtype=np.float64)
    nlev, nlat, nlon = field.shape

    # Compute theta on all pressure levels
    # p_levels is 1D, broadcast to 3D
    p_3d = p_levels[:, np.newaxis, np.newaxis] * np.ones((1, nlat, nlon))
    theta_3d = potential_temperature(T, p_3d, p0=p0, kappa=kappa)

    field_theta = np.full((nlat, nlon), np.nan)
    p_theta = np.full((nlat, nlon), np.nan)

    for j in range(nlat):
        for i in range(nlon):
            theta_col = theta_3d[:, j, i]
            field_col = field[:, j, i]
            p_col = p_levels.copy()

            # Remove NaN
            valid = ~(np.isnan(theta_col) | np.isnan(field_col))
            if np.sum(valid) < 2:
                continue

            theta_v = theta_col[valid]
            field_v = field_col[valid]
            p_v = p_col[valid]

            # Check if theta_target is within range
            if theta_target < theta_v.min() or theta_target > theta_v.max():
                continue

            # Sort by theta
            sort_idx = np.argsort(theta_v)
            theta_s = theta_v[sort_idx]
            field_s = field_v[sort_idx]
            p_s = p_v[sort_idx]

            # Linear interpolation in theta-space
            field_theta[j, i] = np.interp(theta_target, theta_s, field_s)

            if log_p:
                p_theta[j, i] = np.exp(
                    np.interp(theta_target, theta_s, np.log(p_s))
                )
            else:
                p_theta[j, i] = np.interp(theta_target, theta_s, p_s)

    return field_theta, p_theta


def interpolate_to_theta_vectorized(field, T, p_levels, theta_target,
                                     p0=1000.0, kappa=0.286):
    """
    Vectorized version of interpolate_to_theta using numpy searchsorted.

    Significantly faster than the loop version for large grids.

    Parameters
    ----------
    field : ndarray, shape (nlev, nlat, nlon)
    T : ndarray, shape (nlev, nlat, nlon)
    p_levels : array_like, shape (nlev,)
    theta_target : float

    Returns
    -------
    field_theta : ndarray, shape (nlat, nlon)
    """
    p_levels = np.asarray(p_levels, dtype=np.float64)
    nlev, nlat, nlon = field.shape

    # Compute theta on all levels
    p_3d = p_levels[:, np.newaxis, np.newaxis] * np.ones((1, nlat, nlon))
    theta_3d = potential_temperature(T, p_3d, p0=p0, kappa=kappa)

    # Reshape to (nlev, npoints) for vectorized processing
    npts = nlat * nlon
    theta_2d = theta_3d.reshape(nlev, npts)
    field_2d = field.reshape(nlev, npts)

    result = np.full(npts, np.nan)

    # For each column, find the two levels bracketing theta_target
    # and linearly interpolate
    for k in range(nlev - 1):
        theta_lo = theta_2d[k, :]
        theta_hi = theta_2d[k + 1, :]
        field_lo = field_2d[k, :]
        field_hi = field_2d[k + 1, :]

        # Find columns where theta_target is between levels k and k+1
        # Handle both increasing and decreasing theta with level
        between = (
            ((theta_lo <= theta_target) & (theta_target <= theta_hi)) |
            ((theta_hi <= theta_target) & (theta_target <= theta_lo))
        )

        # Skip if no points found or all NaN
        if not np.any(between):
            continue

        # Linear interpolation weight
        dtheta = theta_hi[between] - theta_lo[between]
        # Avoid division by zero
        safe = np.abs(dtheta) > 1e-10
        idx = np.where(between)[0]

        w = np.zeros_like(dtheta)
        w[safe] = (theta_target - theta_lo[between][safe]) / dtheta[safe]
        w = np.clip(w, 0.0, 1.0)

        interp_vals = field_lo[between] * (1 - w) + field_hi[between] * w
        result[idx] = interp_vals

    return result.reshape(nlat, nlon)
