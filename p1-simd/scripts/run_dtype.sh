#!/usr/bin/env bash
# Experiment 5: f32 vs f64 vs i32 (same *bytes* footprint, so f64 has half the elements) for all kernels.
source "$(dirname "$0")/common.sh"; init_exp dtype
if [ "$QUICK" = 1 ]; then WS="16,131072"; else WS="16,512,8192,262144"; fi
for k in saxpy dot mul stencil; do for t in f32 f64 i32; do for b in ${BUILDS:-scalar sse avx2 znver5 znver5_fm}; do
  skip_build "$b" "$k" "$t" && continue
  bench "$b" --kernel "$k" --type "$t" --ws-kib "$WS"
done; done; done
