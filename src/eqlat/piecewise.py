"""
Piecewise-constant method for equivalent latitude computation.

For threshold q₀, the enclosed area A(q₀) is the area WHERE PV > q₀
(the poleward cap, measured from the North Pole). Then:

    φ_e = arcsin(1 - A / (2π R²))

This convention gives:
    A = 0          →  φ_e = 90°N  (North Pole)
    A = 2π R²      →  φ_e = 0°    (Equator)
    A = 4π R²      →  φ_e = -90°S (South Pole)

Works for both hemispheres with a single formula.
"""

import numpy as np
from .utils import grid_cell_areas, area_to_eqlat


def equivalent_latitude_piecewise(pv, lat, lon, pv_thresholds=None,
                                   n_thresholds=100):
    """
    Compute equivalent latitude using the piecewise-constant method.

    Parameters
    ----------
    pv : ndarray, shape (nlat, nlon)
        2D potential vorticity field on an isentropic surface.
    lat : array_like, shape (nlat,)
        Latitude values in degrees.
    lon : array_like, shape (nlon,)
        Longitude values in degrees.
    pv_thresholds : array_like, optional
        PV threshold values. If None, n_thresholds linearly-spaced values
        between the field min and max are used.
    n_thresholds : int, optional
        Number of thresholds. Default: 100.

    Returns
    -------
    dict with keys:
        'pv_thresholds' : ndarray
        'eqlat'         : ndarray  (degrees)
        'area'          : ndarray  (m²)
    """
    pv   = np.asarray(pv,   dtype=np.float64)
    lat  = np.asarray(lat,  dtype=np.float64)
    lon  = np.asarray(lon,  dtype=np.float64)

    areas    = grid_cell_areas(lat, lon)
    pv_flat  = pv.ravel()
    ar_flat  = areas.ravel()

    valid      = ~np.isnan(pv_flat)
    pv_valid   = pv_flat[valid]
    ar_valid   = ar_flat[valid]

    if pv_thresholds is None:
        pv_thresholds = np.linspace(pv_valid.min(), pv_valid.max(), n_thresholds)
    else:
        pv_thresholds = np.asarray(pv_thresholds, dtype=np.float64)

    # Sort PV DESCENDING → cumulative area = area(PV ≥ pv_sorted[k])
    # A(q₀) = area(PV > q₀)  →  φ_e = arcsin(1 - A / 2πR²) works globally.
    desc_idx        = np.argsort(-pv_valid)
    pv_desc         = pv_valid[desc_idx]   # descending
    ar_desc         = ar_valid[desc_idx]
    cumarea         = np.cumsum(ar_desc)   # cumarea[k] = area where PV ≥ pv_desc[k]

    # Negate both so we can use searchsorted on an ascending array
    neg_pv_desc     = -pv_desc             # ascending

    area_values = np.empty_like(pv_thresholds)
    for i, q0 in enumerate(pv_thresholds):
        # k = number of elements where pv_desc > q0
        #   = first index in neg_pv_desc where neg_pv_desc >= -q0
        k = int(np.searchsorted(neg_pv_desc, -q0, side='left'))
        area_values[i] = cumarea[k - 1] if k > 0 else 0.0

    eqlat = area_to_eqlat(area_values)
    return {'pv_thresholds': pv_thresholds, 'eqlat': eqlat, 'area': area_values}


def eqlat_field_piecewise(pv, lat, lon, n_thresholds=200):
    """Map every grid-point PV value to its equivalent latitude."""
    res   = equivalent_latitude_piecewise(pv, lat, lon, n_thresholds=n_thresholds)
    eqmap = np.interp(pv.ravel(), res['pv_thresholds'], res['eqlat'])
    return eqmap.reshape(pv.shape)
