#!/usr/bin/env bash
# Experiment 1: scalar vs auto-vectorized (SSE2 / AVX2 / znver5) for each kernel, f32, size sweep.
# Metrics: time, GFLOP/s, GiB/s, cycles/element; speedup computed by process.py.
source "$(dirname "$0")/common.sh"; init_exp speedup
if [ "$QUICK" = 1 ]; then SIZES="16,1024,131072"; else SIZES="8,16,32,48,128,512,1024,4096,16384,65536,262144,1048576"; fi
for k in saxpy dot mul stencil; do for b in ${BUILDS:-$ALL_BUILDS}; do
    skip_build "$b" "$k" f32 && continue
    bench "$b" --kernel "$k" --type f32 --ws-kib "$SIZES"
done; done
