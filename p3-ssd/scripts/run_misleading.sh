#!/usr/bin/env bash
# Exp 7: misleading-setup demos.
#  (a) buffered (direct=0) vs direct=1 reads over a 1 GiB span: page cache inflates buffered numbers.
#      The buffered runs use invalidate=0 and a deliberate warm-up read of the span first. (fio's default
#      invalidate=1 drops the file's page cache at job start -- and, for time_based sequential jobs,
#      on every wrap -- so buffered seq reads would silently go to the SSD: verified, 28 GiB of
#      device reads during a 4 s buffered 128K run over a 1 GiB span.) Page-cache residency
#      (fincore) is recorded before/after in buffered_cache_state.txt. No root / drop_caches needed.
#  (b) buffered vs direct random writes (no fsync) over 1 GiB (size-capped like every write job)
#  (c) wrong effective QD: iodepth=32 with the sync engine psync => effective QD 1
source "$(dirname "$0")/common.sh"; common_init "$@"
MIS_SPAN="${MIS_SPAN:-1G}"
begin_experiment misleading
warm_cache() {  # sequential buffered read of the span into the page cache (not recorded as a result)
  [[ "$DRY" == 1 ]] && return 0
  guard_target "$TESTFILE"
  fio --name=warm --filename="$TESTFILE" --allow_file_create=0 --rw=read --bs=1m --size="$MIS_SPAN" \
      --direct=0 --invalidate=0 --ioengine=psync --cpus_allowed="$CPUS_SINGLE" > "$EXP_DIR/warm_cache.log" 2>&1
  { echo "== $1 $(date -Iseconds)"; fincore "$TESTFILE" 2>&1; } >> "$EXP_DIR/buffered_cache_state.txt"
}
for d in 1 0; do
  inv=1; [[ $d == 0 ]] && { inv=0; warm_cache "after warm-up"; }
  run_fio "randread_4k_direct${d}"  RW=randread BS=4k   IODEPTH=32 SPAN=$MIS_SPAN DIRECT=$d INVALIDATE=$inv DEMO=cache
  run_fio "seqread_128k_direct${d}" RW=read     BS=128k IODEPTH=32 SPAN=$MIS_SPAN DIRECT=$d INVALIDATE=$inv DEMO=cache
  run_fio "randwrite_4k_direct${d}" RW=randwrite BS=4k  IODEPTH=32 SPAN=$MIS_SPAN DIRECT=$d INVALIDATE=$inv DEMO=cachew
done
[[ "$DRY" == 1 ]] || { echo "== after buffered runs $(date -Iseconds)"; fincore "$TESTFILE" 2>&1; } >> "$EXP_DIR/buffered_cache_state.txt"
run_fio "randread_4k_uring_qd32"  RW=randread BS=4k IODEPTH=32                  DEMO=qd
run_fio "randread_4k_psync_qd32"  RW=randread BS=4k IODEPTH=32 IOENGINE=psync   DEMO=qd
run_fio "randread_4k_uring_qd1"   RW=randread BS=4k IODEPTH=1                   DEMO=qd
end_experiment
