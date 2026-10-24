#!/usr/bin/env bash
# Parse raw fio output and make all figures/tables (run from anywhere; uses common/pyrun.sh: a venv or uv).
# Missing experiments are skipped with a message.
cd "$(dirname "$0")/../.." || exit 1
if [[ "${QUICK:-0}" == 1 ]]; then   # same output redirection as common.sh: QUICK data never mixes with final data
  q="$PWD/p3-ssd/scratch/sanity"; export RAW_DIR="${RAW_DIR:-$q/raw}" PROC_DIR="${PROC_DIR:-$q/processed}" FIG_DIR="${FIG_DIR:-$q/figures}"
fi
bash common/pyrun.sh p3-ssd/scripts/parse_fio.py || exit 1
for p in qd1 bs rwmix qd_sweep tail workingset sustained misleading; do
  bash common/pyrun.sh "p3-ssd/scripts/plot_$p.py" || echo "(plot_$p skipped/failed)"
done
