#!/bin/bash
#SBATCH --account=co2
#SBATCH --qos=batch
#SBATCH --job-name=dl_MERRA2
#SBATCH --partition=orion
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=10G
#SBATCH --time=08:00:00
#SBATCH --output=/work2/noaa/co2/jesswein/logs/%x_%j.out
#SBATCH --error=/work2/noaa/co2/jesswein/logs/%x_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=markus.jesswein@noaa.gov
###############################################################################
#  SLURM job: Download MERRA-2 EPV & T on pressure levels for a full year
#
#  Usage:
#      sbatch submit_download_MERRA2.sh 2023
#      sbatch submit_download_MERRA2.sh 2023 /work2/noaa/co2/jesswein/data/MERRA2
#
#  Arguments:
#      $1  Year to download  (required)
#      $2  Output directory   (optional, default: $DATA/MERRA2)
###############################################################################

set -eo pipefail

# ---------- Argument handling ----------
YEAR=${1:?  "ERROR: Year argument required.  Usage: sbatch submit_download_MERRA2.sh YEAR [OUTDIR]"}
OUTDIR=${2:-${DATA:-/work2/noaa/co2/jesswein/data}/MERRA2}

echo "============================================"
echo "  MERRA-2 Download Job"
echo "  Year    : $YEAR"
echo "  Outdir  : $OUTDIR"
echo "  Job ID  : $SLURM_JOB_ID"
echo "  Node    : $HOSTNAME"
echo "  Started : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"

# ---------- Environment ----------
module purge
module load python/3.10.8

source /work2/noaa/co2/miniconda3/etc/profile.d/conda.sh
conda activate ccgg

# Now enable strict unset-variable checking (after conda, which uses unset vars)
set -u

# ---------- Run ----------
python "${HOME}/eqlat_HPC/scripts/download_MERRA_2_new.py" "$YEAR" --outdir "$OUTDIR"

echo ""
echo "============================================"
echo "  Finished : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"
