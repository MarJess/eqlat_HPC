from pathlib import Path
import earthaccess

earthaccess.login(strategy='netrc')

data_dir = Path(__file__).parents[2] / "data"
mls_dir = data_dir / "satellite" 

def download_mls(date1=None, date2=None): 
    """
    Dowlonad MLS data for on day 

    Parameters
    ----------
    date : str of the daz in format "YYYY-MM_DD
        
    No retrun, but downloads the Ozone and Temperature data in the mls directory 
    """
    results_o3 = earthaccess.search_data(
    short_name="ML2O3",
    version="005", # Latest version as of 2026 is typically 5
    temporal=(date1, date2),
    count=10
    )

    # results_n2o = earthaccess.search_data(
    # short_name="ML2N2O",
    # version="005", # Latest version as of 2026 is typically 5
    # temporal=(date, date),
    # count=10
    # )

    results_T = earthaccess.search_data(
        short_name="ML2T",
        version="005", # Latest version as of 2026 is typically 5
        temporal=(date1, date2),
        count=10
    )

    mls_dir.mkdir(parents=True, exist_ok=True)
    earthaccess.download(results_o3 + results_T, local_path=mls_dir)
    print('Download successful!')


# ---------------------------------------------------------------------------
#  CLI entry point
# ---------------------------------------------------------------------------
def main():
    """Download MLS O3 and T for a given date range."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Download MLS O3 and Temperature data for a date range."
    )
    parser.add_argument("date1", type=str, help="Start date, e.g. 2023-01-01")
    parser.add_argument("date2", type=str, help="End date,   e.g. 2023-01-31")
    args = parser.parse_args()

    print(f"=== MLS download: {args.date1} → {args.date2} ===")
    print(f"    Output directory: {mls_dir}")

    download_mls(date1=args.date1, date2=args.date2)

    print("=== Finished MLS download ===")


if __name__ == "__main__":
    main()