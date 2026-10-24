#!/usr/bin/env bash
# Full pipeline: build -> all experiments -> process -> plots.
#   scripts/run_all.sh                      # real data into data/raw, data/processed, figures
#   QUICK=1 OUT_ROOT=$PWD/data/raw/sanity scripts/run_all.sh   # smoke test (see README)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
source "$HERE/common.sh"
( cd "$ROOT" && make -j8 )
for s in vecreport bandwidth speedup locality align_tail stride_gather dtype; do "$HERE/run_$s.sh"; done
REL="${OUT_ROOT#$ROOT/}"; PROC="data/processed${REL#data/raw}"; FIG="figures${REL#data/raw}"
cd "$(dirname "$ROOT")"
bash common/pyrun.sh p1-simd/scripts/process.py --raw "p1-simd/$REL" --out "p1-simd/$PROC"
for p in speedup locality align_tail stride_gather dtype roofline; do
  bash common/pyrun.sh "p1-simd/scripts/plot_$p.py" --proc "p1-simd/$PROC" --fig "p1-simd/$FIG"
done
