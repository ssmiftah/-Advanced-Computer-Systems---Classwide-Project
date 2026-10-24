#!/usr/bin/env bash
# Exp 5: tail latency at mid-QD and near-knee QD (4K random read; also 70/30 mix).
# TAIL_QDS defaults to "<mid> <knee>"; knee is read from data/processed/knee.txt (written
# by plot_qd_sweep.py; run_all.sh runs it right after exp 4) if present, else 32.
# The 70/30 mix is a write job: size-capped at W_IO_CAP like every write job (common.sh). Uses json+ clat histogram bins.
source "$(dirname "$0")/common.sh"; common_init "$@"
knee=""; [[ -f "$PROC_DIR/knee.txt" ]] && knee=$(awk '$1=="iodepth" && $2=="randread"{print $3}' "$PROC_DIR/knee.txt")
knee="${knee:-32}"; mid=$(( knee / 4 )); (( mid < 4 )) && mid=4    # mid-QD = knee/4 (>= 4)
dflt TAIL_QDS "$mid $knee" "4 32"
dflt TAIL_RUNTIME 60 5
begin_experiment tail
for qd in $TAIL_QDS; do
  run_fio "randread_qd${qd}" RW=randread BS=4k IODEPTH=$qd RUNTIME=$TAIL_RUNTIME
  run_fio "randrw70_qd${qd}" RW=randrw RWMIX=70 BS=4k IODEPTH=$qd RUNTIME=$TAIL_RUNTIME
done
end_experiment
