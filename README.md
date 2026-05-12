# eqlat_HPC — Equivalent Latitude Computation for NOAA HPC Orion

A Python package for computing **equivalent latitude** (φ_e) from potential vorticity (PV) fields on isentropic surfaces. Supports ERA5 and MERRA-2 reanalysis data.

## Background

Equivalent latitude maps PV isolines to latitudes of equal enclosed area, providing a dynamically consistent coordinate for stratospheric tracer analysis. For a PV threshold q₀:

```
A(q₀) = area where PV > q₀
φ_e   = arcsin(1 − A / (2π R²))
```

## Methods

| Method | Module | Description |
|---|---|---|
| **Piecewise** | `eqlat.piecewise` | Traditional piecewise-constant method |
| **ROI** | `eqlat.roi_fast` | Region of Interest method (Añel et al., 2013) |
| **SWOOSH** | `eqlat.swoosh` | Ozone-based equivalent latitude for ozonesonde profiles |

The ROI method uses contour integration for more accurate area estimation, especially for complex PV distributions with holes or dateline crossings.


### Dependencies

```
numpy
xarray
scipy
contourpy
tqdm        	# optional, for progress bars
cdsapi      	# optional, for ERA5 downloads
earthaccess 	# optional, for MERRA-2 downloads
```

## Quick Start

### Single PV field

```python
import numpy as np
from eqlat import equivalent_latitude_piecewise, equivalent_latitude_roi

# pv: 2D array (nlat, nlon) on one isentropic surface [PVU]
result = equivalent_latitude_roi(pv, lat, lon, n_thresholds=200)

print(result["pv_thresholds"])  # PV values
print(result["eqlat"])          # equivalent latitudes [°N]
```

### Full equivalent latitude map

```python
from eqlat.roi_fast import eqlat_field_roi
from eqlat.piecewise import eqlat_field_piecewise

eqlat_map = eqlat_field_roi(pv, lat, lon)   # shape (nlat, nlon)
```


### Batch processing — PV on pressure levels (ERA5 / MERRA-2)

```python
from eqlat.batch import process_pressure_netcdf

theta_levels = [320, 340, 350, 360, 380, 400, 500, 600, 700, 800]

ds = process_pressure_netcdf(
    "MERRA2_400.inst3_3d_asm_Np.20050101.nc4",
    theta_levels=theta_levels,
    method="roi",
    n_workers=4,        # parallel processing
)
ds["eqlat"].sel(theta=380).isel(time=0).plot()
```

### Ozonesonde equivalent latitude via SWOOSH

```python
from eqlat.swoosh import equivalent_latitude_swoosh_new
import xarray as xr
import numpy as np

swoosh_ds = xr.open_dataset("path_to_SWOOSH_product")

eqlat, o3_ref = equivalent_latitude_swoosh_new(
    swoosh_ds,
    sonde_theta=theta_array,       # potential temperature [K]
    sonde_o3=o3_array,             # ozone mixing ratio [ppmv]
    sonde_time=np.datetime64("2005-01-15"),
)
```

## Scripts

| Script | Description |
|---|---|
| `scripts/download_ERA_5.py` | Download ERA5 PV + temperature from CDS |
| `scripts/download_MERRA_2_new.py` | Download MERRA-2 PV + temperature |
| `scripts/merge_reanalysis.py` | Merge reanalysis files |
| `scripts/process_fields.py` | Batch compute equivalent latitude fields |

### Batch processing from the command line

```bash
python scripts/process_fields.py \
    --indir  /data/era5/pv \
    --outdir /data/era5/eqlat \
    --model  ERA5 \
    --roi
```


## Package Structure

```
eqlat/
├── eqlat/
│   ├── piecewise.py      # piecewise-constant method
│   ├── roi_fast.py       # ROI method (contourpy-based)
│   ├── swoosh.py         # SWOOSH ozone method
│   ├── interpolation.py  # pressure → isentropic interpolation
│   ├── batch.py          # NetCDF batch processing
│   └── utils.py          # grid-cell areas, coordinate helpers
├── scripts/
    ├── download_ERA_5.py
    ├── download_MERRA_2_new.py
    ├── merge_reanalysis.py
    └── process_fields.py

```

## Reference

Añel JA, Allen DR, Sáenz G, Gimeno L, de la Torre L (2013).  
*Equivalent Latitude Computation Using Regions of Interest (ROI).*  
PLoS ONE 8(9): e72970. https://doi.org/10.1371/journal.pone.0072970

## License

MIT License — see [LICENSE](LICENSE).
