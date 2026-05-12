"""
Equivalent Latitude Computation Package
========================================

Implements two methods for computing equivalent latitude (φ_e):
1. Piecewise-constant method (traditional)
2. Region of Interest (ROI) method (Añel et al., 2013)

Both methods compute φ_e from 2D fields of potential vorticity (PV)
on isentropic surfaces.

Reference:
    Añel JA, Allen DR, Sáenz G, Gimeno L, de la Torre L (2013)
    Equivalent Latitude Computation Using Regions of Interest (ROI).
    PLoS ONE 8(9): e72970. doi:10.1371/journal.pone.0072970
"""

from .piecewise import equivalent_latitude_piecewise
from .roi_fast import equivalent_latitude_roi
from .utils import grid_cell_areas

__version__ = "0.1.0"
__all__ = [
    "equivalent_latitude_piecewise",
    "equivalent_latitude_roi",
    "grid_cell_areas",
]
