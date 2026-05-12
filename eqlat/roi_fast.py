"""
Region of Interest (ROI) method for equivalent latitude computation.

Robust implementation for real reanalysis data (ERA5, MERRA-2).

Convention (unified NH + SH):
    A(q₀) = area where PV > q₀
    φ_e   = arcsin(1 − A / (2π R²))

    NH thresholds (q₀ ≥ 0):  A = area(PV > q₀)          → φ_e > 0°
    SH thresholds (q₀ < 0):  A = A_total − area(PV < q₀) → φ_e < 0°

Reference:
    Añel JA et al. (2013) PLoS ONE 8(9): e72970.
    doi:10.1371/journal.pone.0072970
"""

import numpy as np
import contourpy

from .utils import grid_cell_areas, area_to_eqlat, R_EARTH


def _ensure_lat_ascending(lat, pv):
    """Return (lat, pv) with latitude running south → north."""
    lat = np.asarray(lat, dtype=np.float64)
    pv  = np.asarray(pv,  dtype=np.float64)
    if lat[0] > lat[-1]:
        lat = lat[::-1]
        pv  = pv[::-1, :]
    return lat, pv


def _ensure_lon_0_360(lon, pv):
    """
    Map any longitude convention to [0, 360) and sort columns.

    Handles ERA5 (−180…180), MERRA-2 (−180…179.375), and 0…360.
    """
    lon = np.asarray(lon, dtype=np.float64).copy()
    pv  = np.asarray(pv,  dtype=np.float64).copy()
    lon = lon % 360.0
    sort_idx = np.argsort(lon)
    return lon[sort_idx], pv[:, sort_idx]


def _signed_spherical_area(lats_deg, lons_deg):
    """
    Signed spherical-polygon area via:  A = −R² ∮ sin(φ) dλ

    Positive for a counter clock wise (CCW) polygon (interior to the left).
    Dateline crossings are handled by wrapping Δλ to (−π, +π].
    """
    lats = np.deg2rad(np.asarray(lats_deg, dtype=np.float64))
    lons = np.deg2rad(np.asarray(lons_deg, dtype=np.float64))
    if len(lats) < 3:
        return 0.0
    if not (np.isclose(lats[0], lats[-1]) and np.isclose(lons[0], lons[-1])):
        lats = np.append(lats, lats[0])
        lons = np.append(lons, lons[0])
    dlon    = np.diff(lons)
    dlon    = (dlon + np.pi) % (2.0 * np.pi) - np.pi
    sin_avg = 0.5 * (np.sin(lats[:-1]) + np.sin(lats[1:]))
    return float(-R_EARTH**2 * np.sum(sin_avg * dlon))


def _sum_contourpy_area(points_list, offsets_list):
    """
    Sum the absolute net signed areas of all polygons from contourpy.

    Parameters
    ----------
    points_list : list of ndarray, shape (n, 2)
        Vertex arrays returned by ``contour_generator.filled()``.
        Each array contains (x=lon, y=lat) columns.
    offsets_list : list of ndarray
        Offset arrays that separate outer boundaries from holes
        within each polygon group.

    Returns
    -------
    float : total enclosed area in m²

    Notes
    -----
    With ``FillType.OuterOffset``, each polygon group can contain an
    outer boundary followed by zero or more interior holes.  The signed
    area formula gives positive area for CCW (outer) sub-paths and
    negative area for CW (hole) sub-paths, so summing gives the correct
    net area per group.  We take ``abs`` of each group sum so that
    polygon winding order ambiguity doesn't matter.
    """
    total = 0.0
    for pts, offs in zip(points_list, offsets_list):
        if len(pts) < 3:
            continue
        # Each offset pair [offs[k], offs[k+1]) is one sub-path
        group_area = 0.0
        for k in range(len(offs) - 1):
            verts = pts[offs[k]:offs[k + 1]]
            if len(verts) >= 3:
                # pts columns are (x=lon, y=lat)
                group_area += _signed_spherical_area(verts[:, 1], verts[:, 0])
        total += abs(group_area)
    return total


def _area_pv_gt_threshold(gen, threshold, pv_min, pv_max,
                           total_valid_area, cell_areas, valid_mask,
                           pv_data):
    """
    Compute A(q₀) = area(PV > q₀) for one threshold.

    Uses a pre-built contourpy ``ContourGenerator`` (passed in from
    the outer loop) to avoid re-creating the generator each iteration.

    Falls back to the piecewise estimate if contouring raises.

    Parameters
    ----------
    gen : contourpy.ContourGenerator
        Pre-built generator (reusable across thresholds).
    threshold : float
    pv_min, pv_max : float  (statistics of the *valid* cells)
    total_valid_area : float  (sum of areas of non-masked cells)
    cell_areas : ndarray, shape (nlat, nlon)
        Pre-computed grid-cell areas.
    valid_mask : ndarray of bool, shape (nlat, nlon)
        True where data is not masked/NaN.
    pv_data : ndarray, shape (nlat, nlon)
        Raw PV values (for piecewise fallback).

    Returns
    -------
    float : area in m²
    """
    # out-of-range shortcuts
    if threshold >= pv_max:
        return 0.0
    if threshold <= pv_min:
        return total_valid_area

    if threshold >= 0:
        # NH: fill where PV > threshold (north-polar cap)
        lev_hi = pv_max + max(abs(pv_max) * 0.01, 1e-6)
        try:
            pts, offs = gen.filled(threshold, lev_hi)
            area = _sum_contourpy_area(pts, offs)
        except Exception:
            area = float(np.sum(
                cell_areas[valid_mask & (pv_data > threshold)]
            ))

    else:
        # SH: fill where PV < threshold (south-polar cap), complement
        lev_lo = pv_min - max(abs(pv_min) * 0.01, 1e-6)
        try:
            pts, offs = gen.filled(lev_lo, threshold)
            area_south = _sum_contourpy_area(pts, offs)
            area       = total_valid_area - area_south
        except Exception:
            area = float(np.sum(
                cell_areas[valid_mask & (pv_data > threshold)]
            ))

    return float(area)


def equivalent_latitude_roi(pv, lat, lon, pv_thresholds=None, n_thresholds=100):
    """
    Compute equivalent latitude using the Region of Interest (ROI) method.

    Robust for real reanalysis data:

    * ERA5  – lat descending (90→−90), lon in [−180, 180] or [0, 360]
    * MERRA-2 – lat ascending, lon in [−180, 179.375]
    * NaN values (surface intersections, masked ocean/land) are properly
      excluded from the contour computation and from the total area.
    * All three contour cases (Cases 1, 2, 3 of Añel et al. 2013)
    * Compound paths with interior holes (isolated lower-PV regions
      surrounded by higher-PV air) are handled correctly via the signed
      spherical area formula.

    Algorithm
    ---------
    1. Normalise grid: lat ascending, lon in [0, 360).
    2. Create a masked array (NaN → masked) so matplotlib excludes
       those cells from contourf.
    3. total_valid_area = sum of grid-cell areas for non-masked cells.
    4. For each PV threshold q₀:

       NH (q₀ ≥ 0):
         contourf([q₀, PV_max])  →  area(PV > q₀)

       SH (q₀ < 0):
         contourf([PV_min, q₀])  →  area_south(PV < q₀)
         A(q₀) = total_valid_area − area_south

    5. φ_e = arcsin(1 − A / (2π R²))

    All three contour cases are handled automatically:
      Case 1 → simple closed polygon(s) from get_paths().
      Case 2 → two polygons (one each side of the dateline); summed.
      Case 3 → polygon extending to the grid top/bottom; the signed
               area formula gives the correct polar-cap area.

    Parameters
    ----------
    pv : ndarray, shape (nlat, nlon)
        Potential vorticity in PVU on an isentropic surface.
        May contain NaN (e.g. where the surface intersects the ground).
    lat : array_like, shape (nlat,)
        Latitudes in degrees. May be ascending or descending.
    lon : array_like, shape (nlon,)
        Longitudes in degrees. May be in [−180, 180] or [0, 360].
    pv_thresholds : array_like, optional
        PV threshold values (PVU). If None, n_thresholds linearly-spaced
        values between the 1st and 99th percentile of the valid cells.
    n_thresholds : int, optional
        Number of threshold values (default 100).

    Returns
    -------
    dict with keys:
        'pv_thresholds' : ndarray, shape (n,)   – PV values (PVU)
        'eqlat'         : ndarray, shape (n,)   – equivalent latitude (°)
        'area'          : ndarray, shape (n,)   – enclosed area (m²)
    """
    pv  = np.asarray(pv,  dtype=np.float64)
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)

    # Normalise grid orientation
    lat, pv = _ensure_lat_ascending(lat, pv)
    lon, pv = _ensure_lon_0_360(lon, pv)

    # Masked array: NaN → masked
    pv_ma = np.ma.masked_invalid(pv)

    # Field statistics (valid cells only)
    pv_min = float(pv_ma.min())
    pv_max = float(pv_ma.max())

    # Total area of valid cells
    cell_areas       = grid_cell_areas(lat, lon)
    valid_mask       = ~np.ma.getmaskarray(pv_ma)   # True where data is good
    total_valid_area = float(np.sum(cell_areas[valid_mask]))

    # PV thresholds
    if pv_thresholds is None:
        pv_thresholds = np.linspace(pv_min, pv_max, n_thresholds)
        # lo = float(np.nanpercentile(pv, 1))
        # hi = float(np.nanpercentile(pv, 99))
        #pv_thresholds = np.linspace(lo, hi, n_thresholds)
    else:
        pv_thresholds = np.asarray(pv_thresholds, dtype=np.float64)

    # Pre-compute grid objects (once)
    lon2d, lat2d = np.meshgrid(lon, lat)

    # Build the contourpy generator once; reuse for every threshold.
    gen = contourpy.contour_generator(
        x=lon2d, y=lat2d, z=pv_ma,
        fill_type=contourpy.FillType.OuterOffset,
        corner_mask=True,
    )

    # Loop over thresholds
    area_values = np.empty_like(pv_thresholds)
    for i, q0 in enumerate(pv_thresholds):
        area_values[i] = _area_pv_gt_threshold(
            gen, q0,
            pv_min, pv_max, total_valid_area,
            cell_areas, valid_mask, pv_ma.data
        )

    # Area to equivalent latitude
    eqlat = area_to_eqlat(area_values)

    return {
        "pv_thresholds": pv_thresholds,
        "eqlat":         eqlat,
        "area":          area_values,
    }


def eqlat_field_roi(pv, lat, lon, n_thresholds=200):
    """
    Compute equivalent latitude at every grid point using the ROI method.

    Builds a PV→φ_e lookup table with n_thresholds entries,
    then interpolates to every grid-point PV value.

    Parameters
    ----------
    pv : ndarray, shape (nlat, nlon)
    lat, lon : array_like
    n_thresholds : int

    Returns
    -------
    eqlat_map : ndarray, shape (nlat, nlon)
    """
    pv  = np.asarray(pv,  dtype=np.float64)
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)

    result       = equivalent_latitude_roi(pv, lat, lon,
                                           n_thresholds=n_thresholds)
    sort_idx     = np.argsort(result["pv_thresholds"])
    pv_sorted    = result["pv_thresholds"][sort_idx]
    eqlat_sorted = result["eqlat"][sort_idx]

    eqlat_map = np.interp(pv.ravel(), pv_sorted, eqlat_sorted)
    return eqlat_map.reshape(pv.shape)
