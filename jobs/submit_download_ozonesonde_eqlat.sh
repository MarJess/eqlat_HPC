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
#  SLURM job: Boulder ozonesonde (GPS-filtered) + matching ERA5/MERRA-2
#
#  Three sequential steps:
#    1. Scrape & download Boulder native-resolution ozonesonde profiles,
#       keeping only those with per-scan GPS latitude/longitude columns.
#       Writes a manifest CSV of the resulting flight dates.
#    2. Download ERA5 PV/T (pressure levels) for exactly those dates.
#    3. Download MERRA-2 EPV/T (pressure levels) for exactly those dates.
#
#  ERA5/MERRA-2 output goes to *separate* directories from the full-year
#  climatology downloads (ERA5_ozonesonde / MERRA2_ozonesonde), so this does
#  not interfere with submit_download_ERA5.sh / submit_download_MERRA2.sh or
#  get auto-picked-up by submit_process_eqlat.sh.
#
#  All three download steps skip files that already exist, so if the job
#  runs out of walltime it is safe to simply re-submit — it will resume
#  where it left off. (Time limit kept at 08:00:00 to match the QOS cap
#  used by the other jobs in this project — a longer --time was rejected
#  with "Job violates accounting/QOS policy".)
#
#  NOTE ON PARTITION: this job uses --partition=service (not orion).
#  Regular `orion` compute nodes have no outbound internet access — only
#  the `service` partition runs on front-end/login nodes with external
#  network connectivity, which is required here for the gml.noaa.gov,
#  CDS (ERA5), and NASA GES DISC (MERRA-2) HTTP(S) requests. `service`
#  is capped at 1 core / 24h, which matches this job's resource request.
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
###############################################################################

set -eo pipefail

# ---------- Argument handling ----------
YEAR_START=${1:-2005}
YEAR_END=${2:-2025}

O3_URL=${3:-"https://gml.noaa.gov/aftp/data/ozwv/Ozonesonde/Boulder,%20Colorado/Native%20Resolution%20(60s,%207s,%201s)/"}

DATA_ROOT=${DATA:-/work2/noaa/co2/jesswein/data}
O3_OUTDIR="${DATA_ROOT}/ozonesonde"
MANIFEST="${O3_OUTDIR}/gps_dates_manifest.csv"
ERA5_OUTDIR="${DATA_ROOT}/ERA5_ozonesonde"
MERRA2_OUTDIR="${DATA_ROOT}/MERRA2_ozonesonde"

echo "============================================"
echo "  Ozonesonde (GPS) + ERA5/MERRA-2 Download Job"
echo "  Years        : $YEAR_START - $YEAR_END"
echo "  Sonde URL    : $O3_URL"
echo "  Sonde outdir : $O3_OUTDIR"
echo "  Manifest     : $MANIFEST"
echo "  ERA5 outdir  : $ERA5_OUTDIR"
echo "  MERRA2 outdir: $MERRA2_OUTDIR"
echo "  Job ID       : $SLURM_JOB_ID"
echo "  Node         : $HOSTNAME"
echo "  Started      : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"

module purge
source /work2/noaa/co2/miniconda3/etc/profile.d/conda.sh

# ---------- Step 1: Ozonesonde download with GPS filter ----------
# Needs requests, beautifulsoup4, pandas, numpy.
conda activate ccgg

echo ""
echo "### Step 1/3: Ozonesonde download (GPS lat/lon filter) ###"
python "${HOME}/eqlat_HPC/src/download/download_ozonesondes.py" \
    --year-start "$YEAR_START" \
    --year-end   "$YEAR_END" \
    --url        "$O3_URL" \
    --outdir     "$O3_OUTDIR" \
    --manifest   "$MANIFEST"

conda deactivate

N_DATES=$(($(wc -l < "$MANIFEST") - 1))
echo ""
echo "Manifest has $N_DATES GPS-equipped flight dates."

if [ "$N_DATES" -le 0 ]; then
    echo "No GPS-equipped ozonesonde dates found — skipping ERA5/MERRA-2 download."
    exit 0
fi

# ---------- Step 2: ERA5 for those dates ----------
conda activate e5

echo ""
echo "### Step 2/3: ERA5 download for manifest dates ###"
python "${HOME}/eqlat_HPC/src/download/download_ERA_5.py" \
    --dates-file "$MANIFEST" \
    --outdir     "$ERA5_OUTDIR"

conda deactivate

# ---------- Step 3: MERRA-2 for those dates ----------
conda activate ccgg

echo ""
echo "### Step 3/3: MERRA-2 download for manifest dates ###"
python "${HOME}/eqlat_HPC/src/download/download_MERRA_2_new.py" \
    --dates-file "$MANIFEST" \
    --outdir     "$MERRA2_OUTDIR"

conda deactivate

echo ""
echo "============================================"
echo "  Finished : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"
