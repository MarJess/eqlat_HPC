#!/bin/bash
#SBATCH --account=co2
#SBATCH --qos=batch
#SBATCH --job-name=dl_o3sonde_eqlat
#SBATCH --partition=service
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=10G
#SBATCH --time=08:00:00
#SBATCH --output=/work2/noaa/co2/jesswein/logs/%x_%j.out
#SBATCH --error=/work2/noaa/co2/jesswein/logs/%x_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=markus.jesswein@noaa.gov
###############################################################################
#  SLURM job: Download Boulder ozonesonde data
#
#  NOTE: this currently only runs the ozonesonde download (one call per
#  year, using download_ozonesondes.py's original single-year CLI).
#  The GPS lat/lon filtering, flight-date manifest, and the follow-on
#  ERA5/MERRA-2-for-matching-dates steps were reverted (2026-07-20) while
#  debugging a connection issue to gml.noaa.gov and are NOT part of this
#  script anymore. Re-add them once download_ozonesondes.py has GPS
#  filtering + a manifest again — see project memory / chat history for
#  the previous 3-step version (scrape+filter -> ERA5 -> MERRA-2).
#
#  Usage:
#      sbatch submit_download_ozonesonde_eqlat.sh
#      sbatch submit_download_ozonesonde_eqlat.sh 2005 2025
#      sbatch submit_download_ozonesonde_eqlat.sh 2005 2025 "https://gml.noaa.gov/aftp/data/ozwv/Ozonesonde/Boulder,%20Colorado/Native%20Resolution%20(60s,%207s,%201s)/"
#
#  Arguments:
#      $1  Start year  (optional, default: 2005)
#      $2  End year    (optional, default: 2025)
#      $3  Ozonesonde base URL (optional, default: NOAA GML Boulder, CO)
#
#  NOTE ON PARTITION: this job uses --partition=service (not orion).
#  Regular `orion` compute nodes have no outbound internet access — only
#  the `service` partition runs on front-end/login nodes with external
#  network connectivity, needed here for the gml.noaa.gov requests.
#  `service` is capped at 1 core / 24h, matching this job's resources.
###############################################################################

set -eo pipefail

# ---------- Argument handling ----------
YEAR_START=${1:-2005}
YEAR_END=${2:-2025}
O3_URL=${3:-"https://gml.noaa.gov/aftp/data/ozwv/Ozonesonde/Boulder,%20Colorado/Native%20Resolution%20(60s,%207s,%201s)/"}

DATA_ROOT=${DATA:-/work2/noaa/co2/jesswein/data}
O3_OUTDIR="${DATA_ROOT}/ozonesonde"

echo "============================================"
echo "  Ozonesonde Download Job"
echo "  Years        : $YEAR_START - $YEAR_END"
echo "  Sonde URL    : $O3_URL"
echo "  Sonde outdir : $O3_OUTDIR"
echo "  Job ID       : $SLURM_JOB_ID"
echo "  Node         : $HOSTNAME"
echo "  Started      : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"

module purge
source /work2/noaa/co2/miniconda3/etc/profile.d/conda.sh

# Needs requests, beautifulsoup4, pandas, numpy.
conda activate ccgg

for YEAR in $(seq "$YEAR_START" "$YEAR_END"); do
    echo ""
    echo "### Ozonesonde download for $YEAR ###"
    python "${HOME}/eqlat_HPC/src/download/download_ozonesondes.py" \
        "$YEAR" \
        --url    "$O3_URL" \
        --outdir "$O3_OUTDIR"
done

conda deactivate

echo ""
echo "============================================"
echo "  Finished : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"
