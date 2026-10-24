#!/usr/bin/env bash
# Create + precondition the test file (regular file inside p3-ssd/, never a device).
# Sequentially writes TESTFILE_SIZE (default 32G) of incompressible random data with
# direct=1 so every block is really allocated AND written (a sparse/fallocated-only
# file would read back zeros without touching flash).
# Optional: PRECOND_RAND_GIB=N adds N GiB of 4K random writes (QD32) afterwards.
# Env: TESTFILE_SIZE, TESTFILE, FORCE=1 (rewrite even if already prepared), QUICK=1.
# Flags: --yes, --estimate
source "$(dirname "$0")/common.sh"; common_init "$@"
PRECOND_RAND_GIB="${PRECOND_RAND_GIB:-0}"
size_b=$(to_bytes "$TESTFILE_SIZE")
if [[ "$DRY" == 1 ]]; then
  v=$(awk -v b=$size_b -v r=$PRECOND_RAND_GIB 'BEGIN{printf "%.3f", b/1073741824+r}')
  echo "prepare fill $((size_b/1000000000/3+1)) $v $v" >> "${ESTIMATE_FILE:-/dev/null}"; exit 0
fi
guard_target "$TESTFILE"
if [[ -f "$TESTFILE" && -f "$TESTFILE.precond" && "${FORCE:-0}" != 1 && $(stat -c %s "$TESTFILE") == "$size_b" ]]; then
  echo "already prepared ($TESTFILE, $TESTFILE_SIZE); use FORCE=1 to redo"; exit 0
fi
check_free_space "$size_b"
echo "Will write $TESTFILE_SIZE (+${PRECOND_RAND_GIB} GiB random) to $TESTFILE"
confirm "Proceed?"
rm -f "$TESTFILE" "$TESTFILE.precond"
mkdir -p "$RAW_DIR/prepare"
fio --name=precondition_fill --filename="$TESTFILE" --rw=write --bs=1M --size="$TESTFILE_SIZE" \
    --direct=1 --ioengine="$ENGINE" --iodepth=16 --refill_buffers --randrepeat=0 \
    --buffer_compress_percentage=0 --end_fsync=1 --cpus_allowed="$CPUS_SINGLE" \
    --output-format=json --output="$RAW_DIR/prepare/fill.json" || die "fill failed"
if awk -v r="$PRECOND_RAND_GIB" 'BEGIN{exit !(r>0)}'; then
  fio --name=precondition_rand --filename="$TESTFILE" --allow_file_create=0 --rw=randwrite --bs=4k --size="$TESTFILE_SIZE" \
      --io_size="${PRECOND_RAND_GIB}G" --direct=1 --ioengine="$ENGINE" --iodepth=32 --refill_buffers --randrepeat=0 \
      --cpus_allowed="$CPUS_SINGLE" --output-format=json --output="$RAW_DIR/prepare/rand.json" || die "random precondition failed"
fi
alloc=$(( $(stat -c %b "$TESTFILE") * 512 )); sz=$(stat -c %s "$TESTFILE")
(( sz == size_b )) || die "size mismatch: $sz != $size_b"
(( alloc >= sz )) || die "file not fully allocated (alloc=$alloc size=$sz)"
echo "size=$sz alloc=$alloc date=$(date -Iseconds) pattern=incompressible" > "$TESTFILE.precond"
echo "OK: $TESTFILE fully written ($((sz>>20)) MiB), allocated=$((alloc>>20)) MiB"
