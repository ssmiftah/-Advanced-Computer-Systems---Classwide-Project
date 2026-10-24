#!/usr/bin/env bash
# Exp 4: queue depth / parallelism sweep (throughput-vs-latency, knee, Little's Law).
# Series A: numjobs=1, iodepth in QD_LIST (default 1..256).
# Series B: iodepth=1, numjobs in JOBS_LIST (default 1..64; fio processes on CPUS_MULTI).
# Ops (QD_OPS, default "randread randwrite"), bs QD_BS (default 4k). direct=1, full span.
# Write ops use the reduced lists QD_W_LIST / JOBS_W_LIST (SSD wear; points are size-capped, common.sh W_*).
source "$(dirname "$0")/common.sh"; common_init "$@"
dflt QD_LIST "1 2 4 8 16 32 64 128 256" "1 4 16 64 256"
dflt JOBS_LIST "1 2 4 8 16 32 64" "1 4 16"
dflt QD_W_LIST "1 2 4 8 16 32 128" "1 16 128"
dflt JOBS_W_LIST "1 4 16" "1 4"
dflt QD_OPS "randread randwrite" "randread randwrite"
dflt QD_BS 4k 4k
begin_experiment qd_sweep
for op in $QD_OPS; do
  ql=$QD_LIST; jl=$JOBS_LIST; [[ $op == *write* || $op == randrw ]] && { ql=$QD_W_LIST; jl=$JOBS_W_LIST; }
  for qd in $ql;  do run_fio "${op}_iodepth${qd}" RW=$op BS=$QD_BS IODEPTH=$qd NUMJOBS=1 SERIES=iodepth; done
  for nj in $jl; do run_fio "${op}_numjobs${nj}" RW=$op BS=$QD_BS IODEPTH=1 NUMJOBS=$nj SERIES=numjobs; done
done
end_experiment
