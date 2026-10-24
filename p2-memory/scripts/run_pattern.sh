#!/usr/bin/env bash
# Experiment 2: access pattern (seq vs random) and granularity (stride 64/128/256/1024 B)
# -> latency (pointer chase) and bandwidth (bandwidth.c), at an L2-resident and a DRAM-sized buffer.
# Bandwidth: access=64 reads one full line per block; access=8 reads one 8 B word per
# block (useful bytes << line bytes: shows effective vs line bandwidth).
# The DRAM buffer is 1 GiB per thread so that even at stride 1024 B the set of distinct lines
# touched (size/stride x 64 B = 64 MiB) is larger than the 32 MiB L3 of a CCD; with 256 MiB it
# would be only 16 MiB of lines, i.e. potentially L3-resident rather than DRAM.
set -eu
source "$(dirname "$0")/lib.sh"
mkout pattern
if [[ "$QUICK" == 1 ]]; then LS="262144 268435456"; BS_L2=$((512*KiB)); BS_DRAM=$((64*MiB)); STR="64 256 1024"; TC="1 $NT"
else LS="262144 8388608 536870912"; BS_L2=$((512*KiB)); BS_DRAM=$((1*GiB)); STR="64 128 256 1024"; TC="1 $NT"; fi
# latency
for pat in seq random; do for st in $STR; do for s in $LS; do
  steps=$(( s >= 8*MiB ? 3000000 : 10000000 )); [[ "$QUICK" == 1 ]] && steps=$((steps/10))
  append "$D/latency.csv" taskset -c "$CPU" "$BIN/latency" --size "$s" --pattern "$pat" --stride "$st" \
      --pages thp --steps "$steps" --reps "$REPS_LAT" --cycles
done; done; done
# bandwidth
for t in $TC; do for bs in $BS_L2 $BS_DRAM; do for pat in seq rand; do for st in $STR; do for acc in 64 8; do
  append "$D/bandwidth.csv" "$BIN/bandwidth" --size "$bs" --threads "$t" --cpus "$(cpus_n "$t")" \
      --pattern "$pat" --stride "$st" --access "$acc" --rw 1:0 --pages thp --secs "$SECS" --reps "$REPS_BW"
done; done; done; done; done
