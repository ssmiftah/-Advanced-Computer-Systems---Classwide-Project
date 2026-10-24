#!/usr/bin/env bash
# Exp 6a: working-set / LBA-range. 4K random read (QD32) and 4K random write (QD32)
# restricted to the first SPAN bytes of the file; spans in WS_SPANS (<= TESTFILE_SIZE).
source "$(dirname "$0")/common.sh"; common_init "$@"
dflt WS_SPANS "1G 2G 4G 8G 16G 32G" "1G 2G"
dflt WS_OPS "randread randwrite" "randread randwrite"
dflt WS_W_SPANS "1G 4G 32G" "1G"     # write spans (reduced: wear); each point size-capped (W_IO_CAP)
begin_experiment workingset
for sp in $WS_SPANS; do
  (( $(to_bytes $sp) <= $(to_bytes $TESTFILE_SIZE) )) || continue
  for op in $WS_OPS; do
    [[ $op == *write* && " $WS_W_SPANS " != *" $sp "* ]] && continue
    run_fio "${op}_span${sp}" RW=$op BS=4k IODEPTH=32 SPAN=$sp; done
done
# always include the full file as the last point
[[ " $WS_SPANS " == *" $TESTFILE_SIZE "* ]] || run_fio "randread_spanfull" RW=randread BS=4k IODEPTH=32 SPAN=$TESTFILE_SIZE
end_experiment
