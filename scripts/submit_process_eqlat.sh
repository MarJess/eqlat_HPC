#!/bin/bash
#SBATCH --account=co2
#SBATCH --qos=batch
#SBATCH --job-name=eqlat
#SBATCH --partition=orion
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=10G
#SBATCH --time=08:00:00
#SBATCH --output=/work2/noaa/co2/jesswein/logs/%x_%j.out
#SBATCH --error=/work2/noaa/co2/jesswein/logs/%x_%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=markus.jesswein@noaa.gov
###############################################################################
#  SLURM job: Compute equivalent latitude from ERA5/MERRA-2 fields
#
#  Processes ALL input files sequentially (both piecewise + roi methods).
#  Already computed files are automatically skipped.
#
#  Usage:
#      sbatch submit_process_eqlat.sh ERA5
#      sbatch submit_process_eqlat.sh MERRA2
#      sbatch submit_process_eqlat.sh ERA5 /custom/indir /custom/outdir
#
#  Arguments:
#      $1  Model type: ERA5 or MERRA2  (required)
#      $2  Input directory   (optional, default: $DATA/ERA5_12UTC or $DATA/MERRA2_12UTC)
#      $3  Output directory  (optional, default: $RESULTS/eqlat_ERA5_12UTC or $RESULTS/eqlat_MERRA2_12UTC)
###############################################################################

set -eo pipefail

# ---------- Argument handling ----------
MODEL=${1:?  "ERROR: Model argument required (ERA5 or MERRA2)."}

if [ "$MODEL" == "ERA5" ]; then
    INDIR=${2:-${DATA:-/work2/noaa/co2/jesswein/data}/ERA5_12UTC}
    OUTDIR=${3:-${RESULTS:-/work2/noaa/co2/jesswein/results}/eqlat_ERA5_12UTC}
elif [ "$MODEL" == "MERRA2" ]; then
    INDIR=${2:-${DATA:-/work2/noaa/co2/jesswein/data}/MERRA2_12UTC}
    OUTDIR=${3:-${RESULTS:-/work2/noaa/co2/jesswein/results}/eqlat_MERRA2_12UTC}
else
    echo "ERROR: Model must be ERA5 or MERRA2, got: $MODEL"
    exit 1
fi

echo "============================================"
echo "  Equivalent Latitude Calculation"
echo "  Model      : $MODEL"
echo "  Input dir  : $INDIR"
echo "  Output dir : $OUTDIR"
echo "  Job ID     : $SLURM_JOB_ID"
echo "  Node       : $HOSTNAME"
echo "  CPUs       : $SLURM_CPUS_PER_TASK"
echo "  Started    : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"

# ---------- Environment ----------
source /work2/noaa/co2/miniconda3/etc/profile.d/conda.sh
conda activate /work2/noaa/co2/jesswein/conda_envs/ccgg_clone

set -u

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

# ---------- Run ----------
python "${HOME}/eqlat_HPC/scripts/process_fields.py" \
    --indir  "$INDIR" \
    --outdir "$OUTDIR" \
    --model  "$MODEL" \
    --roi

echo ""
echo "============================================"
echo "  Finished : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"
