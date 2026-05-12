"""
Utility functions for equivalent latitude computations.
"""

import numpy as np

# Earth's radius in meters
R_EARTH = 6.371e6  # m


def grid_cell_areas(lat, lon):
    """
    Compute the area of each grid cell on a regular lat-lon grid.

    Uses the formula:
        A_grid = 2π R² Δ(sin φ) / n_lon

    where Δ(sin φ) is the difference in sin(latitude) across the cell
    and n_lon is the number of longitude points.

    Parameters
    ----------
    lat : array_like, shape (nlat,)
        Latitude values in degrees (must be evenly spaced).
    lon : array_like, shape (nlon,)
        Longitude values in degrees (must be evenly spaced).

    Returns
    -------
    areas : ndarray, shape (nlat, nlon)
        Area of each grid cell in m².
    """
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)

    nlat = len(lat)
    nlon = len(lon)

    # Compute latitude bin edges
    dlat = np.abs(lat[1] - lat[0]) if nlat > 1 else 180.0
    lat_edges = np.zeros(nlat + 1)
    lat_edges[1:-1] = 0.5 * (lat[:-1] + lat[1:])
    lat_edges[0] = max(lat[0] - dlat / 2, -90.0)
    lat_edges[-1] = min(lat[-1] + dlat / 2, 90.0)

    # Sort edges so that they go from south to north
    lat_edges = np.sort(lat_edges)

    # Compute longitude bin width
    dlon = np.abs(lon[1] - lon[0]) if nlon > 1 else 360.0
    dlon_rad = np.deg2rad(dlon)

    # Area for each latitude band
    sin_edges = np.sin(np.deg2rad(lat_edges))
    delta_sin = np.abs(np.diff(sin_edges))

    # Map back to original latitude ordering
    lat_sorted_idx = np.argsort(lat)
    lat_inv_idx = np.argsort(lat_sorted_idx)
    delta_sin_ordered = delta_sin[lat_inv_idx]

    # Area = R² * dlon * delta_sin for each cell
    area_1d = R_EARTH**2 * dlon_rad * delta_sin_ordered
    areas = np.broadcast_to(area_1d[:, np.newaxis], (nlat, nlon)).copy()

    return areas


def total_sphere_area():
    """Total area of Earth's surface in m²."""
    return 4.0 * np.pi * R_EARTH**2


def area_to_eqlat(area):
    """
    Convert enclosed area (from North Pole) to equivalent latitude.

    φ_e = arcsin(1 - A / (2π R²))

    Parameters
    ----------
    area : float or array_like
        Enclosed area in m², measured from the North Pole.

    Returns
    -------
    eqlat : float or ndarray
        Equivalent latitude in degrees.
    """
    area = np.asarray(area, dtype=np.float64)
    arg = 1.0 - area / (2.0 * np.pi * R_EARTH**2)
    arg = np.clip(arg, -1.0, 1.0)
    return np.rad2deg(np.arcsin(arg))


def eqlat_to_area(eqlat):
    """
    Convert equivalent latitude to enclosed area (from North Pole).

    A = 2π R² (1 - sin(φ_e))

    Parameters
    ----------
    eqlat : float or array_like
        Equivalent latitude in degrees.

    Returns
    -------
    area : float or ndarray
        Enclosed area in m².
    """
    eqlat = np.asarray(eqlat, dtype=np.float64)
    return 2.0 * np.pi * R_EARTH**2 * (1.0 - np.sin(np.deg2rad(eqlat)))

