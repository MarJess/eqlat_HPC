import argparse
from pathlib import Path
import xarray as xr

def merge_datasets(indir, wildcard, outdir, outname):
    # Use Path for robust OS-independent path handling
    input_path = Path(indir)
    output_path = Path(outdir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Create the full glob pattern
    search_pattern = str(input_path / wildcard)
    print(search_pattern)
    
    print(f"Opening files matching: {search_pattern}")
    
    # parallel=True speeds up reading if dask is installed
    # chunks={} ensures the data is treated as a dask array (lazy loading)
    with xr.open_mfdataset(
        search_pattern, 
        combine='by_coords', 
        parallel=True, 
        chunks={'time': 10} 
    ) as ds:
        
        target_file = output_path / outname
        print(f"Saving merged dataset to: {target_file}")
        
        # Using netcdf4 engine is standard for pressure surface data
        ds.to_netcdf(target_file, engine='h5netcdf')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge PV on pressure surfaces")
    parser.add_argument("--indir", type=str, required=True, help="Directory containing input files")
    parser.add_argument("--wildcard_name", type=str, required=True, help="Pattern e.g., 'pv_*.nc'")
    parser.add_argument("--outdir", type=str, required=True, help="Directory to save output")
    parser.add_argument("--outname", type=str, required=True, help="Name of output file")

    args = parser.parse_args()

    merge_datasets(args.indir, args.wildcard_name, args.outdir, args.outname)
