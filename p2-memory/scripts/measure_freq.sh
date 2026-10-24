#!/usr/bin/env bash
# Measure the actual core clock while a core is busy chasing pointers, two ways:
#  (1) in-process: user-space cycles counter (perf_event_open) / wall time over the
#      timed loop (latency --cycles, column core_ghz);
#  (2) cross-check with perf stat: cycles:u / task-clock, counters gated to the
#      timed region via --control fifos.
# Usage: scripts/measure_freq.sh [cpu] [size_bytes]   (default cpu 4, 16 KiB = L1)
set -eu
source "$(dirname "$0")/lib.sh"
cpu="${1:-$CPU}"; size="${2:-16384}"
echo "# (1) in-process cycles / time"
taskset -c "$cpu" "$BIN/latency" --size "$size" --steps 20000000 --reps 5 --cycles --header
echo "# (2) perf stat cross-check (ghz = cycles / task-clock-ns)"
PERF_OUT="$(mktemp)"; PERF_PROG_OUT=/dev/null
perf_run "cycles:u,task-clock" taskset -c "$cpu" "$BIN/latency" --size "$size" --steps 20000000 --reps 5
awk -F, '/cycles/ {c=$1} /task-clock/ {t=$1} END {printf "perf: cycles=%s task_clock_ms=%s => %.3f GHz\n", c, t, c/(t*1e6)}' "$PERF_OUT"
rm -f "$PERF_OUT"
