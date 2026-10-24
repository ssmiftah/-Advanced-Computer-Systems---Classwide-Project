#!/usr/bin/env bash
# Experiment 4: access intensity -> throughput vs latency curves.
#  (a) MLP sweep: T threads x K interleaved chains (outstanding = T*K), DRAM-sized.
#  (b) MLC-style: 1 latency probe + (NT-1) streaming threads with injected delay.
set -eu
source "$(dirname "$0")/lib.sh"
mkout intensity
if [[ "$QUICK" == 1 ]]; then KS="1 4 16"; TS="1 2"; DELAYS="0 200 5000"; SZ=$((128*MiB))
else KS="1 2 3 4 5 6 8 10 12 16 20 24 32 48 64"; TS="$(thread_counts)"; DELAYS="0 5 10 20 40 80 160 320 640 1280 2560 10000"; SZ=$((256*MiB)); fi
for t in $TS; do for k in $KS; do
  append "$D/mlp.csv" "$BIN/mlp" --size "$SZ" --threads "$t" --cpus "$(cpus_n "$t")" --chains "$k" \
      --pages thp --secs "$SECS" --reps "$REPS_BW"
done; done
BG="${THREAD_CPUS#*,}"; NBG=$((NT-1))
for d in $DELAYS; do
  append "$D/loaded_latency.csv" "$BIN/mlp" --size "$SZ" --chains 1 --cpus "${TCPU[0]}" --bg "$NBG" \
      --bgcpus "$BG" --bgdelay "$d" --bgrw 1:0 --bgsize $((128*MiB)) --secs "$SECS" --reps "$REPS_BW"
done
