#!/usr/bin/env bash
# Experiment 8: benchmark pitfalls, each shown side by side with the correct version.
#  P1 "DRAM" test whose footprint fits the 32 MiB-per-CCD L3 (16 MiB) vs a real DRAM footprint;
#     latency chase and read bandwidth.
#  P2 lazy allocation: reading never-written (untouched) anonymous memory maps the shared
#     zero page / huge zero page, so a "1 GiB" buffer behaves like a tiny cached one (--nowarm).
#  P3 careless pinning: two threads "pinned to two CPUs" that are SMT siblings of ONE core
#     (cpu N and N+16 on this machine) vs two distinct physical cores. The siblings share the
#     core's load ports, L1d and L2, so an L1-resident test loses ~half its bandwidth and two
#     768 KiB buffers (1.5 MiB together) no longer fit the shared 1 MiB L2. (Plain unpinned vs
#     pinned showed no difference on an idle machine: the scheduler does not migrate busy
#     threads, so that variant was dropped.)
# (Frequency pitfall: the core_ghz column of latency.csv records the real clock; changing the
#  governor needs sudo so it is not toggled by these scripts.)
set -eu
source "$(dirname "$0")/lib.sh"
mkout pitfall
FAKE=$((16*MiB)); REAL=$((1*GiB)); [[ "$QUICK" == 1 ]] && REAL=$((256*MiB))
for s in $((4*MiB)) $FAKE $REAL; do
  append "$D/p1_latency.csv" taskset -c "$CPU" "$BIN/latency" --size "$s" --pattern random --pages thp \
      --steps $([[ "$QUICK" == 1 ]] && echo 400000 || echo 3000000) --reps "$REPS_LAT" --cycles
  append "$D/p1_bandwidth.csv" "$BIN/bandwidth" --size "$s" --threads 1 --cpus "$CPU" --secs "$SECS" --reps "$REPS_BW"
done
# 4 threads x 16 MiB on one CCD = 64 MiB > 32 MiB L3 -> truly DRAM, vs 4 x 4 MiB = 16 MiB (L3-resident)
for s in $((4*MiB)) $FAKE; do
  append "$D/p1_bandwidth.csv" "$BIN/bandwidth" --size "$s" --threads 4 --cpus 4,5,6,7 --secs "$SECS" --reps "$REPS_BW"
done
for pg in thp 4k; do
  append "$D/p2_nowarm.csv" "$BIN/bandwidth" --size "$REAL" --threads 1 --cpus "$CPU" --pages "$pg" --nowarm --secs "$SECS" --reps "$REPS_BW"
  append "$D/p2_nowarm.csv" "$BIN/bandwidth" --size "$REAL" --threads 1 --cpus "$CPU" --pages "$pg" --secs "$SECS" --reps "$REPS_BW"
done
# P2: column prefault=0 marks the --nowarm rows (thp_frac is ~0 for them because nothing is
# mapped yet when smaps is sampled; it is also 0 for every 4k row, so it cannot tell them apart).
SIB=$((CPU + 16))   # SMT sibling of $CPU (siblings are N and N+16 on the 9950X)
for cpus in "$CPU,$((CPU + 1))" "$CPU,$SIB"; do for s in $((16*KiB)) $((768*KiB)); do
  append "$D/p3_pinning.csv" "$BIN/bandwidth" --size "$s" --threads 2 --cpus "$cpus" --secs "$SECS" --reps "$REPS_BW"
done; done
