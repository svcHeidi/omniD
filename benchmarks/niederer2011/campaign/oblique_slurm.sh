#!/bin/bash
# One array task = one job of the oblique-wall study: one scheme, one wall variant, one dx, its three
# time steps (README, "Oblique-wall study (hex)"). Submit once per dx; the ranks and the time limit
# follow the mesh, and --parallel is the allocation's rank count, so --ntasks is the rank count:
#   sbatch --export=ALL,DX=0.5 --ntasks=1  --time=00:30:00 --array=0-5 oblique_slurm.sh
#   sbatch --export=ALL,DX=0.2 --ntasks=8  --time=01:00:00 --array=0-5 oblique_slurm.sh
#   sbatch --export=ALL,DX=0.1 --ntasks=16 --time=02:00:00 --array=0-5 oblique_slurm.sh
# Array task t is scheme (godunov, sbdf2)[t / 3] with variant (0, A, AB)[t % 3].
#
# Edit the partition below (and add --account, --qos or --mem if the site wants them) and the paths in the
# block after the #SBATCH lines.
#SBATCH --job-name=oblique
#SBATCH --nodes=1
#SBATCH --partition=EDIT_PARTITION
#SBATCH --output=oblique-%A_%a.out
set -euo pipefail

# --- edit: this cluster's paths ---
VENV=/EDIT/venv                                  # holds the five omnidriver wheels (README, "Prerequisites")
NATIVE_TUTORIALS=/EDIT/cardiacFoam/tutorials     # the native tree with obliqueWall/, built into the cardiacFoam below
OPENFOAM_BASHRC=/EDIT/OpenFOAM-v2412/etc/bashrc  # the OpenFOAM v2412 that cardiacFoam was built with
CAMPAIGN=/EDIT/omnidriver/benchmarks/niederer2011/campaign  # the omniD checkout at the recorded commit
# module load EDIT_COMPILER EDIT_MPI             # whatever OpenFOAM's bashrc expects, if the site uses modules
# --- end of edits ---

for path in "$VENV/bin/python" "$NATIVE_TUTORIALS" "$OPENFOAM_BASHRC" "$CAMPAIGN/campaign.sh"; do
  [ -e "$path" ] || { echo "oblique_slurm.sh: $path does not exist; edit the paths at the top of this script" >&2; exit 2; }
done
: "${DX:?submit with --export=ALL,DX=0.5 (or 0.2, 0.1)}"
[ -d "$CAMPAIGN/runs" ] || { echo "oblique_slurm.sh: $CAMPAIGN/runs is missing; link it to scratch first (README, \"Layout\")" >&2; exit 2; }

export OMP_NUM_THREADS=1
export PYTHON="$VENV/bin/python" OMNIDRIVER_NATIVE_TUTORIALS="$NATIVE_TUTORIALS" OPENFOAM_BASHRC
schemes=(godunov sbdf2) variants=(0 A AB)
task=$SLURM_ARRAY_TASK_ID
cd "$CAMPAIGN"
./campaign.sh oblique "${schemes[task / 3]}" "${variants[task % 3]}" "$DX" "$SLURM_NTASKS"
