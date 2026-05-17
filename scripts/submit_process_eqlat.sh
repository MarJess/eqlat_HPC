#!/bin/bash
#SBATCH --account=co2
#SBATCH --qos=batch
#SBATCH --job-name=eqlat
#SBATCH --partition=orion
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=10G
#SBATCH --time=08:00:00
#SBATCH --output=/work2/noaa/co2/jesswein/logs/%x_%A_%a.out
#SBATCH --error=/work2/noaa/co2/jesswein/logs/%x_%A_%a.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=markus.jesswein@noaa.gov
###############################################################################
#  SLURM Array-Job: Compute equivalent latitude from ERA5/MERRA-2 fields
#
#  Each array task processes ONE input file (both piecewise + roi methods).
#
#  Usage:
#      # Count input files first:
#      N=$(ls $PROJECT/data/ERA5_12UTC/*pv* | wc -l)
#      echo "Number of files: $N"
#
#      # Submit array job (0-indexed):
#      sbatch --array=0-$((N-1)) submit_process_eqlat.sh ERA5
#
#      # Or limit concurrent tasks (e.g. max 20 at a time):
#      sbatch --array=0-$((N-1))%20 submit_process_eqlat.sh ERA5
#
#  Arguments:
#      $1  Model type: ERA5 or MERRA2  (required)
#      $2  Input directory   (optional, default: $DATA/ERA5_12UTC or $DATA/MERRA2_12UTC)
#      $3  Output directory  (optional, default: $RESULTS/eqlat_ERA5 or $RESULTS/eqlat_MERRA2)
###############################################################################

set -eo pipefail

# ---------- Argument handling ----------
MODEL=${1:?  "ERROR: Model argument required (ERA5 or MERRA2)."}

if [ "$MODEL" == "ERA5" ]; then
    INDIR=${2:-${DATA:-/work2/noaa/co2/jesswein/data}/ERA5_12UTC}
    OUTDIR=${3:-${RESULTS:-/work2/noaa/co2/jesswein/results}/eqlat_ERA5}
elif [ "$MODEL" == "MERRA2" ]; then
    INDIR=${2:-${DATA:-/work2/noaa/co2/jesswein/data}/MERRA2_12UTC}
    OUTDIR=${3:-${RESULTS:-/work2/noaa/co2/jesswein/results}/eqlat_MERRA2}
else
    echo "ERROR: Model must be ERA5 or MERRA2, got: $MODEL"
    exit 1
fi

echo "============================================"
echo "  Equivalent Latitude Calculation"
echo "  Model      : $MODEL"
echo "  Input dir  : $INDIR"
echo "  Output dir : $OUTDIR"
echo "  Array Task : $SLURM_ARRAY_TASK_ID"
echo "  Job ID     : $SLURM_ARRAY_JOB_ID"
echo "  Node       : $HOSTNAME"
echo "  CPUs       : $SLURM_CPUS_PER_TASK"
echo "  Started    : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"

# ---------- Environment ----------
#module purge

source /work2/noaa/co2/miniconda3/etc/profile.d/conda.sh
conda activate ccgg

set -u

export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK

# ---------- Run ----------
python "${HOME}/eqlat_HPC/scripts/process_fields.py" \
    --indir  "$INDIR" \
    --outdir "$OUTDIR" \
    --model  "$MODEL" \
    --roi \
    --index  "$SLURM_ARRAY_TASK_ID"

echo ""
echo "============================================"
echo "  Finished : $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================"
