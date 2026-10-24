#!/usr/bin/env bash
# Exp 1: QD=1 latency. 4KiB random R/W and 128KiB sequential R/W, iodepth=1, 1 job.
# Fixed: direct=1, full-file span, incompressible data. Varied: pattern x op.
source "$(dirname "$0")/common.sh"; common_init "$@"
begin_experiment qd1
run_fio randread_4k   RW=randread  BS=4k   IODEPTH=1
run_fio randwrite_4k  RW=randwrite BS=4k   IODEPTH=1
run_fio seqread_128k  RW=read      BS=128k IODEPTH=1
run_fio seqwrite_128k RW=write     BS=128k IODEPTH=1
end_experiment
