#!/usr/bin/env bash
# Optional: data-pattern check. Same jobs with COMPRESS=0 (incompressible, the default for every
# experiment), 50 and 100 (% compressible buffers) to see if the controller compresses.
source "$(dirname "$0")/common.sh"; common_init "$@"
begin_experiment pattern
for c in 0 50 100; do
  run_fio "seqwrite_128k_c$c" RW=write     BS=128k IODEPTH=16 COMPRESS=$c
  run_fio "randwrite_4k_c$c"  RW=randwrite BS=4k   IODEPTH=32 COMPRESS=$c
done
end_experiment
