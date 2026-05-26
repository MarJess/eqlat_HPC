import os

import numpy as np
import xarray as xr
import xesmf as xe
import pandas as pd

def calc_diff(era5_dir, 
              merra2_dir,
              method='piecewise'):
    """
    Calculate the gridded difference in equivalent latitude between ERA5 and MERRA-2.

    All NetCDF files in each directory are combined into a single dataset via
    ``xr.open_mfdataset``. ERA5 is then regridded to the MERRA-2 grid using
    bilinear interpolation before the difference is computed.

    Parameters
    ----------
    era5_dir : str
        Path to the directory containing ERA5 equivalent latitude NetCDF files.
    merra2_dir : str
        Path to the directory containing MERRA-2 equivalent latitude NetCDF files.
    method : str, optional
        Computation method used to produce the equivalent latitude files.
        Matched against the filename glob ``*{method}_*.nc``.
        Supported values are ``'piecewise'`` (default) and ``'roi'``.

    Returns
    -------
    xr.DataArray
        Difference ``ERA5 - MERRA-2`` equivalent latitude on the MERRA-2 grid,
        with dimensions ``(time, theta, lat, lon)``.
    """

    # Open datasets with optimized chunking
    # Chunking by 'theta' allows Dask to parallelize across levels
    ds_s = xr.open_mfdataset(f'{era5_dir}/*{method}_*.nc', combine='by_coords')
    ds_s = ds_s.rename({'valid_time': 'time'})
    ds_m = xr.open_mfdataset(f'{merra2_dir}/*{method}_*.nc', combine='by_coords')

    # Regrid (broadcasts automatically across theta and time)
    regridder = xe.Regridder(ds_s, ds_m, 'bilinear', periodic=True)
    ds_s_regridded = regridder(ds_s)

    # Define the Difference
    diff = ds_s_regridded['eqlat'] - ds_m['eqlat']

    return diff 


def calculate_seasonal_stats(da, theta_levels, regions):
    """
    Calculate Mean Bias and RMSD across isentropic levels, seasons, and regions.

    This function performs area-weighted spatial averaging on a difference 
    DataArray. It computes statistics for each 
    unique combination of the provided isentropic levels, meteorological 
    seasons, and geographical latitude bands.

    Parameters
    ----------
    da : xr.DataArray
        The input difference field. Must contain dimensions (time, theta, lat, lon).
        'time' should be a datetime-like coordinate to allow seasonal grouping.
    theta_levels : list of float
        The specific isentropic potential temperature levels (in Kelvin) 
        to analyze. Uses 'nearest' neighbor lookups.
    regions : dict of {str: slice}
        A dictionary where keys are region names (e.g., 'Tropics') and 
        values are `slice` objects representing latitude ranges 
        (e.g., `slice(-30, 30)`).

    Returns
    -------
    pd.DataFrame
        A long-format DataFrame containing the following columns:
        - 'Theta': The isentropic level.
        - 'Season': The meteorological season (DJF, MAM, JJA, SON).
        - 'Region': The name of the latitude band.
        - 'Mean_Bias': The area-weighted mean of the difference.
        - 'RMSD': The area-weighted Root Mean Square Deviation.
    """
    
    all_results = []
    
    for theta in theta_levels:
        print(f"Processing theta: {theta}K...")
        # Select level and load into memory to speed up seasonal/regional loops
        da_level = da.sel(theta=theta, method='nearest').compute()
        
        # Group by season (DJF, MAM, JJA, SON)
        for season, da_season in da_level.groupby('time.season'):
            
            for region_name, lat_range in regions.items():
                # Subset to latitude
                subset = da_season.sel(lat=lat_range)
                
                # Area weights
                weights = np.cos(np.deg2rad(subset.lat))
                weighted_da = subset.weighted(weights)
                
                # Calculations
                bias = weighted_da.mean(dim=['time', 'lat', 'lon']).values.item()
                
                msd = (subset**2).weighted(weights).mean(dim=['time', 'lat', 'lon'])
                rmsd = np.sqrt(msd).values.item()
                
                all_results.append({
                    "Theta": theta,
                    "Season": season,
                    "Region": region_name,
                    "Mean_Bias": bias,
                    "RMSD": rmsd
                })
                
    return pd.DataFrame(all_results)


# ---------------------------------------------------------------------------
#  CLI entry point
# ---------------------------------------------------------------------------
def main():
    """Compute seasonal bias and RMSD statistics between ERA5 and MERRA-2 equivalent latitude."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Compute seasonal Mean Bias and RMSD between ERA5 and MERRA-2 equivalent latitude."
    )
    parser.add_argument("--era5_indir", type=str, required=True, help="Directory containing ERA5 EqLat files")
    parser.add_argument("--merra2_indir", type=str, required=True, help="Directory containing MERRA-2 EqLat files")
    parser.add_argument(
        "--outdir", type=str,
        default=os.environ.get("RESULTS", ".") + "/diff",
        help="Output directory (default: $RESULTS/diff)"
    )

    parser.add_argument(
        "--method", type=str, default="piecewise",
        help="EqLat method"
    )
    args = parser.parse_args()

    era5_eqlat_dir = args.era5_indir
    merra2_eqlat_dir = args.merra2_indir
    method = args.method
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)

    print(f"=== Reanalysis EqLat statistics ===")
    print(f"    ERA5 input   : {era5_eqlat_dir}")
    print(f"    MERRA-2 input: {merra2_eqlat_dir}")
    print(f"    Method       : {method}")
    print(f"    Output dir   : {outdir}")

    # calc diff 
    diff = calc_diff(era5_eqlat_dir, merra2_eqlat_dir, method)

    # Define the levels
    thetas_to_check = [400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0]

    # Define your regions
    lat_regions = {
        "NH_High": slice(60, 90),
        "NH_Mid": slice(30, 60),
        "Tropics": slice(-30, 30),
        "SH_Mid": slice(-60, -30),
        "SH_High": slice(-90, -60)
    }

    # Run the function
    df_stats = calculate_seasonal_stats(diff, thetas_to_check, lat_regions)

    # save df_stats
    out_path = os.path.join(outdir, f"diff_stats_{method}.csv")
    df_stats.to_csv(out_path, index=False)
    print(f"    Saved stats  : {out_path}")
    print(f"=== Done ===")


if __name__ == "__main__":
    main()