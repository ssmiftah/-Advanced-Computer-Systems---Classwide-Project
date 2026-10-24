#!/usr/bin/env bash
# Experiment 2: working-set sweep (8 KiB .. 1 GiB) crossing L1d (48 KiB), L2 (1 MiB), L3 (32 MiB/CCD), DRAM.
# ws = nominal footprint of all arrays of the kernel; extra points around each boundary.
source "$(dirname "$0")/common.sh"; init_exp locality
if [ "$QUICK" = 1 ]; then SIZES="16,1024,131072"; KERNELS="saxpy"
else
  SIZES="8,12,16,24,32,40,48,56,64,96,128,256,512,768,1024,1280,1536,2048,4096,8192,16384,24576,32768,40960,49152,65536,131072,262144,524288,1048576"
  KERNELS="${KERNELS:-saxpy dot mul stencil}"
fi
for k in $KERNELS; do for b in ${BUILDS:-scalar sse avx2 znver5 znver5_fm}; do
    skip_build "$b" "$k" f32 && continue
    bench "$b" --kernel "$k" --type f32 --ws-kib "$SIZES"
done; done
