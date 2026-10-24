#!/usr/bin/env bash
# Experiment 7: TLB-miss impact. One 64 B node per 4 KiB page, random or sequential page
# order, span from 1 MiB to 4 GiB, with 4 KiB pages vs THP (2 MiB), dTLB counters gated to the
# timed region. Event set: cycles, instructions, L1 dTLB miss, L2 dTLB miss (page walk), DRAM fills.
set -eu
source "$(dirname "$0")/lib.sh"
mkout tlb
EV="cycles,instructions,ls_l1_d_tlb_miss.all,ls_l1_d_tlb_miss.all_l2_miss,ls_any_fills_from_sys.dram_io_all"
if [[ "$QUICK" == 1 ]]; then SPANS="4194304 67108864 536870912"; ORDERS="random"; R=2; STEPS=4000000
else SPANS="$(sizes_octave $MiB $((4*GiB)))"; ORDERS="random seq"; R=5; STEPS=10000000; fi
for o in $ORDERS; do for pg in 4k thp; do for sp in $SPANS; do
  PERF_OUT="$D/perf_tmp.txt"; PERF_PROG_OUT="$D/prog_tmp.csv"
  perf_run "$EV" "$BIN/tlb" --span "$sp" --pages "$pg" --order "$o" --steps "$STEPS" --reps "$R" --cpu "$CPU" --header 2>/dev/null
  csv_add "$D/tlb.csv" "$PERF_PROG_OUT"
  bash "$COMMON/pyrun.sh" "$ROOT/scripts/perf_parse.py" --perf "$PERF_OUT" --prog "$PERF_PROG_OUT" \
      --work-col steps --out "$D/tlb_perf.csv"
done; done; done
rm -f "$D/perf_tmp.txt" "$D/prog_tmp.csv"
