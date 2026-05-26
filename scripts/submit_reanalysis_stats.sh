#!/bin/bash
#SBATCH --account=co2
#SBATCH --qos=batch
#SBATCH --job-name=eqlat_stats
#SBATCH --partition=orion
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=40G
#SBATCH --time=04:00:00
#SBATCH --output=/work2/noaa/co2/jesswein/logs/%x_%j.out
#SBATCH --error=/work2/noaa/co2/jesswein/logs/%x_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=markus.jesswein@noaa.gov
###############################################################################
#  SLURM job: Compute seasonal bias & RMSD between ERA5 and MERRA-2 eqlat
#
#  Usage:
#      sbatch submit_reanalysis_stats.sh
#      sbatch submit_reanalysis_stats.sh piecewise
#      sbatch submit_reanalysis_stats.sh roi
#
#  Arguments:
#      $1  Method: piecewise or roi  (optional, default: piecewise)
###############################################################################

set -eo pipefail

# ---------- Argument handling ----------
METHOD=${1:-piecewise}
ERA5_DIR=${RESULTS:-/work2/noaa/co2/jesswein/results}/eqlat_ERA5_12UTC
MERRA2_DIR=${RESULTS:-/work2/noaa/co2/jesswein/results}/eqlat_MERRA2_12UTC
OUTDIR=${RESULTS:-/work2/noaa/co2/jesswein/results}/diff

echo "============================================"
echo "  Reanalysis EqLat Statistics"
echo "  Method   : $METHOD"
echo "  ERA5     : $ERA5_DIR"
echo "  MERRA-2  : $MERRA2_DIR"
echo "  Output   : $OUTDIR"
echo "  Job ID   : $SLURM_JOB_ID"
echo "  Node     : $HOSTNAME"
echo "  CPUs     : $SLURM_CPUS_PER_TASK"
echo "  Memory   : 40G"
echo "  Started  : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"

# ---------- Environment ----------
source /work2/noaa/co2/miniconda3/etc/profile.d/conda.sh
conda activate ccgg

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

# ---------- Run ----------
python "${HOME}/eqlat_HPC/scripts/reanalysis_stats.py" \
    --era5_indir  "$ERA5_DIR" \
    --merra2_indir "$MERRA2_DIR" \
    --outdir "$OUTDIR" \
    --method "$METHOD"

echo ""
echo "============================================"
echo "  Finished : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"
