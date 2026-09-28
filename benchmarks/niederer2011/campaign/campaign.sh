#!/usr/bin/env bash
# The campaign's commands (README, "Running it"). Every input is supplied:
#   PYTHON                          a Python with omnidriver and both plugins installed (default: python3)
#   OMNIDRIVER_NATIVE_TUTORIALS     cardiacFOAM's native tutorials tree (a directory named tutorials)
#   OPENFOAM_BASHRC                 OpenFOAM's etc/bashrc, sourced for cardiacFOAM only
#   OMNIDRIVER_OPENCARP_TUTORIALS   openCARP's tutorials tree (a directory named tutorials)
#   OPENCARP_MPI_BIN                the bin directory of the MPI openCARP was built against, put first on
#                                   PATH for openCARP only (a bundled-MPICH install: <prefix>/lib/petsc/bin)
#   CAMPAIGN_DYLD_LIBRARY_PATH      macOS only: appended to DYLD_LIBRARY_PATH inside each solver's shell
#   REPORTS_DIR                     compare only: where reports are written (default: runs/reports).
#                                   Reports are written once, so a re-read with a changed reader goes
#                                   to a fresh directory rather than overwriting what is already there.
# Usage:
#   campaign.sh check                              requests unchanged, native case unchanged
#   campaign.sh level <solver> <dx-mm> [N]         one dx of the grid (its three time steps), on N ranks
#   campaign.sh perf <solver> <dx-mm> <dt-ms> <N> <rep>   one case, for the scaling curve
#   campaign.sh compare [request-stem ...]         every request whose cases have completed, or those named
#   campaign.sh summary                            tables from the runs and reports
#   campaign.sh proof                              the dx 0.5 mm level end to end, with N = 1 and 2 (README, "The proof")
# <solver> is cardiacfoam or opencarp; N = 1 runs serial.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNS="$HERE/runs"          # the requests name ../runs/...; make it a link to scratch (README, "Layout")
PYTHON="${PYTHON:-python3}"
STUDY=cartesianConvergence
NATIVE_STUDY=NiedererEtAl2011verification/setup/studies/$STUDY/sweep_hex_convergence.json

die() { echo "campaign.sh: $*" >&2; exit 2; }
need() { [ -n "${!1:-}" ] || die "$1 is not set (see the header of this script)"; }

# The grid in each solver's own study units (cardiacFOAM m and s; openCARP um and us).
dx_value() {  # solver dx-mm
  case "$1:$2" in
    cardiacfoam:0.5) echo 0.0005;; cardiacfoam:0.2) echo 0.0002;; cardiacfoam:0.1) echo 0.0001;;
    opencarp:0.5) echo 500.0;; opencarp:0.2) echo 200.0;; opencarp:0.1) echo 100.0;;
    *) die "no dx $2 mm for $1";;
  esac
}
dt_where() {  # solver dt-ms
  case "$1:$2" in
    cardiacfoam:0.05) echo system/controlDict:deltaT=5e-05;; cardiacfoam:0.01) echo system/controlDict:deltaT=1e-05;;
    cardiacfoam:0.005) echo system/controlDict:deltaT=5e-06;;
    opencarp:0.05) echo nversion.par:dt=50.0;; opencarp:0.01) echo nversion.par:dt=10.0;; opencarp:0.005) echo nversion.par:dt=5.0;;
    *) die "no dt $2 ms for $1";;
  esac
}

# Runs `sweep-run` for one solver in that solver's own environment, from the
# directory holding its tutorials tree (each study's cases_root is "tutorials").
sweep_run() {  # solver spec output N
  local solver=$1 spec=$2 output=$3 n=$4
  if [ "$solver" = cardiacfoam ]; then
    need OMNIDRIVER_NATIVE_TUTORIALS; need OPENFOAM_BASHRC
    # `set --` first: OpenFOAM's bashrc reads its positional arguments as
    # settings and files to source, and would otherwise see this function's.
    ( set -- ; set +eu; source "$OPENFOAM_BASHRC"; set -eu
      [ -n "${CAMPAIGN_DYLD_LIBRARY_PATH:-}" ] && export DYLD_LIBRARY_PATH="${DYLD_LIBRARY_PATH:+$DYLD_LIBRARY_PATH:}$CAMPAIGN_DYLD_LIBRARY_PATH"
      cd "$(dirname "$OMNIDRIVER_NATIVE_TUTORIALS")"
      # OpenFOAM's N is the case's numberOfSubdomains (set in the spec); --parallel takes no count.
      "$PYTHON" -m omnidriver sweep-run --plugin cardiacfoam --spec "$spec" --output-dir "$output" \
        --scratch-dir "$RUNS/scratch" $([ "$n" -gt 1 ] && echo --parallel) )
  else
    need OMNIDRIVER_OPENCARP_TUTORIALS; need OPENCARP_MPI_BIN
    ( export PATH="$OPENCARP_MPI_BIN:$PATH"
      [ -n "${CAMPAIGN_DYLD_LIBRARY_PATH:-}" ] && export DYLD_LIBRARY_PATH="${DYLD_LIBRARY_PATH:+$DYLD_LIBRARY_PATH:}$CAMPAIGN_DYLD_LIBRARY_PATH"
      cd "$(dirname "$OMNIDRIVER_OPENCARP_TUTORIALS")"
      "$PYTHON" -m omnidriver sweep-run --plugin opencarp --spec "$spec" --output-dir "$output" \
        --scratch-dir "$RUNS/scratch" $([ "$n" -gt 1 ] && echo --parallel "$n") )
  fi
}

# One level study: the rows of the solver's study at one dx (and one dt), plus
# the rank count where the case states one (level_study.py adds, never overrides).
level_spec() {  # solver out N where...
  local solver=$1 out=$2 n=$3; shift 3
  local source="$HERE/studies/opencarp_$STUDY.json" sets=()
  if [ "$solver" = cardiacfoam ]; then
    need OMNIDRIVER_NATIVE_TUTORIALS; source="$OMNIDRIVER_NATIVE_TUTORIALS/$NATIVE_STUDY"
    [ "$n" -gt 1 ] && sets=(--set "system/decomposeParDict:numberOfSubdomains=$n")
  fi
  local wheres=(); for w in "$@"; do wheres+=(--where "$w"); done
  "$PYTHON" "$HERE/level_study.py" --study "$source" "${wheres[@]}" ${sets[@]+"${sets[@]}"} --out "$out"
}

case "${1:-}" in
  check)
    need OMNIDRIVER_NATIVE_TUTORIALS
    "$PYTHON" "$HERE/write_requests.py" --check --native-tutorials "$OMNIDRIVER_NATIVE_TUTORIALS"
    if command -v sha256sum >/dev/null; then sum=(sha256sum -c); else sum=(shasum -a 256 -c); fi
    (cd "$HERE/requests" && "${sum[@]}" SHA256SUMS >/dev/null) && echo "requests/SHA256SUMS verifies"
    ;;
  level)
    [ $# -ge 3 ] || die "usage: level <solver> <dx-mm> [N]"
    solver=$2 dx=$3 n=${4:-1}
    spec="$RUNS/studies/${solver}_${STUDY}_dx${dx}_np${n}.json"
    level_spec "$solver" "$spec" "$n" "dx=$(dx_value "$solver" "$dx")"
    sweep_run "$solver" "$spec" "$RUNS/$solver/$STUDY/dx$dx" "$n"
    ;;
  perf)
    [ $# -eq 6 ] || die "usage: perf <solver> <dx-mm> <dt-ms> <N> <rep>"
    solver=$2 dx=$3 dt=$4 n=$5 rep=$6
    spec="$RUNS/studies/${solver}_${STUDY}_dx${dx}_dt${dt}_np${n}.json"
    level_spec "$solver" "$spec" "$n" "dx=$(dx_value "$solver" "$dx")" "$(dt_where "$solver" "$dt")"
    sweep_run "$solver" "$spec" "$RUNS/perf/$solver/dx${dx}_dt${dt}/np$n/rep$rep" "$n"
    ;;
  compare)
    shift
    if [ $# -eq 0 ]; then set -- $(cd "$HERE/requests" && ls *.json | sed 's/\.json$//'); fi
    reports="${REPORTS_DIR:-$RUNS/reports}"
    mkdir -p "$reports"
    for stem in "$@"; do
      request="$HERE/requests/$stem.json" report="$reports/$stem.json"
      [ -f "$request" ] || die "no request $stem"
      if [ -e "$report" ]; then echo "$stem: report exists (written once)"; continue; fi
      # A request whose cases have not all completed would write an `unavailable` report,
      # and a report is written once: wait for the runs instead.
      if ! "$PYTHON" - "$request" <<'EOF'
import json, sys
from pathlib import Path
request = Path(sys.argv[1])
for run in json.loads(request.read_text())["runs"].values():
    manifest = request.parent / run["sweep_output"] / "sweep_manifest.json"
    cases = json.loads(manifest.read_text())["cases"] if manifest.is_file() else []
    if not any(c["case_id"] == run["case_id"] and c["status"] == "completed" for c in cases):
        sys.exit(1)
EOF
      then echo "$stem: not every case it names has completed; not compared"; continue; fi
      "$PYTHON" -m omnidriver compare --comparison-request "$request" --report "$report" >/dev/null
      echo "$stem: $("$PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["status"])' "$report")"
    done
    ;;
  summary)
    "$PYTHON" "$HERE/summarize.py" --runs "$RUNS"
    ;;
  proof)  # the cheapest level only, as the runbook runs every level (README, "The proof")
    "$0" check
    "$0" level opencarp 0.5
    "$0" level cardiacfoam 0.5
    for solver in opencarp cardiacfoam; do for n in 1 2; do "$0" perf "$solver" 0.5 0.05 "$n" 1; done; done
    "$0" compare cross_dx0.5_dt0.05 cross_dx0.5_dt0.01 cross_dx0.5_dt0.005 \
      temporal_opencarp_dx0.5_dt0.05_vs_dt0.01 temporal_opencarp_dx0.5_dt0.01_vs_dt0.005 \
      temporal_cardiacfoam_dx0.5_dt0.05_vs_dt0.01 temporal_cardiacfoam_dx0.5_dt0.01_vs_dt0.005
    "$0" summary
    ;;
  *) sed -n '2,18p' "$0"; exit 2;;
esac
