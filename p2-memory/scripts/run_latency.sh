#!/usr/bin/env bash
# Experiments 1 and 5: zero-queue latency per level + working-set sweep.
# Pointer chase (one dependent load per step), single thread pinned to $CPU.
# Configs: random order with THP, random with 4 KiB pages (shows TLB cost at
# large sizes), sequential (hardware prefetch friendly). --cycles records the
# measured core clock so ns can be converted to cycles with the real frequency.
set -eu
source "$(dirname "$0")/lib.sh"
mkout latency
if [[ "$QUICK" == 1 ]]; then SIZES="16384 524288 8388608 268435456"; else SIZES="$(sizes_octave $((4*KiB)) $((2*GiB)))"; fi
for cfgs in "random thp" "random 4k" "seq thp"; do
  set -- $cfgs; pat=$1; pg=$2
  for s in $SIZES; do
    # fewer steps for big buffers (DRAM misses are slow); still >= 1 lap for n<=steps
    if (( s >= 8*MiB )); then steps=3000000; else steps=20000000; fi
    [[ "$QUICK" == 1 ]] && steps=$(( steps / 10 ))
    append "$D/latency.csv" taskset -c "$CPU" "$BIN/latency" --size "$s" --pattern "$pat" \
        --pages "$pg" --steps "$steps" --reps "$REPS_LAT" --cycles
  done
done
