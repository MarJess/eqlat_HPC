import argparse
from pathlib import Path
import xarray as xr
import os
import logging
import sys
sys.path.append('/Users/jesswein/Documents/python/eqlat_project')

from eqlat import batch

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def process_fields(input_dir, 
                   output_dir, 
                   both_methods=True, 
                   version='ERA5'):
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Use rglob or glob from Pathlib for easier filtering
    if version == 'ERA5':
        fields = sorted(input_path.glob('*pv*'))
        name_prefix = 'era5'
    elif version == 'MERRA2':
        fields = sorted(input_path.glob('*EPV*'))
        name_prefix = 'merra2'
    else:
        raise ValueError(f"Unknown version: {version}")

    theta_levels = [300, 310, 320, 330, 340, 350, 360, 370, 380, 390, 400, 
                    425, 450, 475, 500, 550, 600, 650, 700, 750, 800, 900, 1000]
    
    methods = ['piecewise', 'roi'] if both_methods else ['piecewise']

    for field_path in fields:
        # Date parsing
        if version == 'ERA5':
            date_str = field_path.stem.split('_')[-1]
        elif version == 'MERRA2':
            date_str = field_path.stem.split('_')[-2]

        for m in methods:
            filename = f"{name_prefix}_eqlat_{m}_{date_str}.nc"
            filepath = output_path / filename

            if filepath.exists():
                logging.info(f"Skipping: {filename} already exists.")
                continue

            logging.info(f"Processing {m} for {date_str}...")
            
            try:
                # Assuming field_path needs to be a string for batch.process_pressure_netcdf
                tmp_field = batch.process_pressure_netcdf(str(field_path), 
                                                          theta_levels,
                                                          method=m)
                
                tmp_field.to_netcdf(filepath)
                tmp_field.close() 
                
            except Exception as e:
                logging.error(f"Error processing {field_path.name} with method {m}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate Equivalent Latitude on Isentropic Surfaces")
    parser.add_argument("--indir", type=str, required=True, help="Directory containing input files")
    parser.add_argument("--outdir", type=str, required=True, help="Directory to save output")
    parser.add_argument("--model", type=str, required=True, choices=['ERA5', 'MERRA2'], help="Model type (ERA5 or MERRA2)")
    parser.add_argument("--roi", action="store_true", help="If set, run both piecewise and roi methods")

    args = parser.parse_args()

    # Fixed the call by using explicit keyword arguments
    process_fields(
        input_dir=args.indir, 
        output_dir=args.outdir, 
        version=args.model,
        both_methods=args.roi
    )