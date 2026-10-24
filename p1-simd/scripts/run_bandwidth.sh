#!/usr/bin/env bash
# Roofline inputs: (a) single-thread read bandwidth vs buffer size (L1/L2/L3/DRAM) and triad,
# (b) empirical FMA peak (GFLOP/s, FLOP/cycle, core clock).  Single thread: see README for the
# difference to the multi-thread DRAM bandwidth measured in Project 2.
source "$(dirname "$0")/common.sh"
EXP=bandwidth; OUTDIR="$OUT_ROOT/$EXP"; mkdir -p "$OUTDIR"; "$COMMON/env_capture.sh" "$OUTDIR/env.txt"
echo "pinned cpu: $CPU samples: $SAMPLES repeats: $REPEATS quick: $QUICK" >> "$OUTDIR/env.txt"
if [ "$QUICK" = 1 ]; then SZ="16,1024,65536,262144"; else SZ="8,16,32,48,64,256,512,1024,2048,8192,16384,32768,65536,131072,262144,524288,1048576"; fi
# REPEATS separate processes per mode (fresh allocation each), pooled by process.py
for mode in read triad; do
  for ((r = 0; r < REPEATS; r++)); do
    taskset -c "$CPU" "$BIN/membw" --mode $mode --sizes-kib "$SZ" --samples "$SAMPLES" $([ $r -gt 0 ] && echo --no-header)
  done > "$OUTDIR/membw_$mode.csv"
done
taskset -c "$CPU" "$BIN/peakflops" --samples "$SAMPLES" --min-ms "$([ "$QUICK" = 1 ] && echo 20 || echo 60)" > "$OUTDIR/peakflops.csv"
echo "[bandwidth] -> $OUTDIR"
