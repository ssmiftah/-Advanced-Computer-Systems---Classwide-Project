#!/usr/bin/env bash
# Experiment 6: cache-miss impact on a simple kernel (z=x*y, saxpy) vs footprint/pattern,
# with perf counters gated to the timed region (perf stat --control).
# Event set A: cycles, L1d load misses, L2 *demand* misses (core->L2 requests from L1d/IC that
#              miss; l2_cache_req_stat.ic_dc_miss_in_l2 does NOT include L2 hardware prefetches,
#              which dominate for streaming code), L2 HW-prefetch requests that miss L2 but hit
#              L3, L2 HW-prefetch requests that miss L2 and L3 (go to DRAM), L1d fills from DRAM.
#              Total L2 misses = demand + pf_hit_l3 + pf_miss_l3.
# Event set B: cycles, instructions, dTLB L1 miss, dTLB L2 miss (page walks), L1d fills from
#              L3/other-L2 in the CCX.
# Each (config, event set) is a separate run; <=6 events fit Zen 5's 6 core PMCs, so no
# multiplexing (perf_parse.py records perf's run_pct, which must be 100).
set -eu
source "$(dirname "$0")/lib.sh"
mkout kernel
EV_A="cycles,L1-dcache-load-misses,l2_cache_req_stat.ic_dc_miss_in_l2,l2_pf_miss_l2_hit_l3.l1_dc_l2_hwpf,l2_pf_miss_l2_l3.l1_dc_l2_hwpf,ls_any_fills_from_sys.dram_io_all"
EV_B="cycles,instructions,ls_l1_d_tlb_miss.all,ls_l1_d_tlb_miss.all_l2_miss,ls_any_fills_from_sys.local_ccx"
if [[ "$QUICK" == 1 ]]; then FPS="24576 1572864 12582912 402653184"; CONFIGS="mul:seq:1"; WORK=$((1<<26)); R=2
else FPS="$(sizes_octave $((12*KiB)) $((3*GiB)))"; CONFIGS="mul:seq:1 mul:rand:1 mul:seq:8 saxpy:seq:1"; WORK=$((1<<28)); R=5; fi
for cfg in $CONFIGS; do IFS=: read -r kern pat stride <<< "$cfg"
  for fp in $FPS; do for evs in A B; do
    ev=EV_$evs; PERF_OUT="$D/perf_tmp.txt"; PERF_PROG_OUT="$D/prog_tmp.csv"
    perf_run "${!ev}" "$BIN/kernel_miss" --footprint "$fp" --kernel "$kern" --pattern "$pat" \
        --stride "$stride" --pages thp --work "$WORK" --reps "$R" --cpu "$CPU" --header 2>/dev/null
    csv_add "$D/kernel.csv" "$PERF_PROG_OUT" "$evs"
    bash "$COMMON/pyrun.sh" "$ROOT/scripts/perf_parse.py" --perf "$PERF_OUT" --prog "$PERF_PROG_OUT" \
        --work-col elems --out "$D/kernel_perf.csv" --kv "evset=$evs"
  done; done
done
rm -f "$D/perf_tmp.txt" "$D/prog_tmp.csv"
