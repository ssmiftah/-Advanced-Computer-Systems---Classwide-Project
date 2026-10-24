#!/usr/bin/env bash
# Exp 2: block-size sweep. Random: 4..256 KiB; sequential: 4..1024 KiB; read and write.
# Fixed: direct=1, full span. Varied: bs, pattern, op. Reads at QD in BS_QDS (default "1 32"),
# writes at QD in BS_W_QDS (default "32" only, to limit SSD wear; each write point is size-capped, see common.sh W_*).
source "$(dirname "$0")/common.sh"; common_init "$@"
dflt BS_RAND "4k 16k 32k 64k 128k 256k" "4k 64k 256k"
dflt BS_SEQ  "4k 16k 32k 64k 128k 256k 512k 1m" "4k 128k 1m"
dflt BS_QDS  "1 32" "32"
dflt BS_W_QDS "32" "32"
begin_experiment bs_sweep
for op in read write; do
  if [[ $op == read ]]; then qds=$BS_QDS; else qds=$BS_W_QDS; fi
  for qd in $qds; do
    for bs in $BS_RAND; do run_fio "rand${op}_bs${bs}_qd${qd}" RW=rand$op BS=$bs IODEPTH=$qd PATTERN=random; done
    for bs in $BS_SEQ;  do run_fio "seq${op}_bs${bs}_qd${qd}"  RW=$op      BS=$bs IODEPTH=$qd PATTERN=sequential; done
  done
done
end_experiment
