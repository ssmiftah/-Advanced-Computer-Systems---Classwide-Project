#!/usr/bin/env bash
# Run every experiment (QUICK=1 for the tiny sanity configuration), then see README for
# process.py / plot_*.py. Final collection should happen under controlled settings
# (../common/bench_mode.sh). measure_freq.sh is a standalone helper, not part of the sweep.
set -eu
here="$(dirname "$0")"
for s in run_latency run_pattern run_rwmix run_intensity run_kernel run_tlb run_pitfall; do
  "$here/$s.sh"
done
