#!/usr/bin/env bash
# Experiment 3: read/write mix (100R, 100W, 70/30, 50/50).
#  (a) throughput: bandwidth.c, sequential, DRAM-sized, 1 thread and all threads,
#      normal (write-allocate) stores and non-temporal stores for the write mixes.
#  (b) latency under each mix: mlp.c latency probe (1 dependent chain) on THREAD_CPUS[0]
#      while the other threads stream the mix at several injected delays.
set -eu
source "$(dirname "$0")/lib.sh"
mkout rwmix
if [[ "$QUICK" == 1 ]]; then BS=$((64*MiB)); DELAYS="0 100"; else BS=$((256*MiB)); DELAYS="0 20 60 150 400 1500"; fi
MIXES="1:0 0:1 7:3 1:1"
for t in 1 $NT; do for m in $MIXES; do
  append "$D/bandwidth.csv" "$BIN/bandwidth" --size "$BS" --threads "$t" --cpus "$(cpus_n "$t")" \
      --rw "$m" --pattern seq --pages thp --secs "$SECS" --reps "$REPS_BW"
  if [[ "$m" != 1:0 ]]; then
    append "$D/bandwidth.csv" "$BIN/bandwidth" --size "$BS" --threads "$t" --cpus "$(cpus_n "$t")" \
        --rw "$m" --nt --pattern seq --pages thp --secs "$SECS" --reps "$REPS_BW"
  fi
done; done
BG="${THREAD_CPUS#*,}"; NBG=$((NT-1))
append "$D/loaded_latency.csv" "$BIN/mlp" --size $((256*MiB)) --chains 1 --cpus "${TCPU[0]}" --secs "$SECS" --reps "$REPS_BW"
for m in $MIXES; do for d in $DELAYS; do
  append "$D/loaded_latency.csv" "$BIN/mlp" --size $((256*MiB)) --chains 1 --cpus "${TCPU[0]}" \
      --bg "$NBG" --bgcpus "$BG" --bgdelay "$d" --bgrw "$m" --bgsize $((128*MiB)) --secs "$SECS" --reps "$REPS_BW"
done; done
