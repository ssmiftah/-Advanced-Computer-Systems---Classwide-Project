#!/usr/bin/env bash
# Experiment 4: unit stride vs stride 2/4/8 vs gather (random permutation / blocked-random index).
# x is read at x[i*stride] or x[idx[i]]; n (FLOPs) is fixed.  Kernels with a reduction (dot) and
# without (saxpy).  n = element counts chosen so that the *unit-stride* x,y footprint is L1 / L2 /
# L3 / DRAM sized.
source "$(dirname "$0")/common.sh"; init_exp stride_gather
if [ "$QUICK" = 1 ]; then NS="2048,262144"; STRIDES="1 2 8"
else NS="2048,16384,131072,1048576,4194304,16777216"; STRIDES="1 2 4 8"; fi
for k in saxpy dot; do for b in ${BUILDS:-scalar sse avx2 znver5 znver5_fm}; do
  skip_build "$b" "$k" f32 && continue
  bench "$b" --kernel "$k" --type f32 --n "$NS"                              # unit-stride kernel (control)
  for s in $STRIDES; do bench "$b" --kernel "$k" --type f32 --variant stride --stride "$s" --n "$NS"; done
  for g in perm block; do bench "$b" --kernel "$k" --type f32 --variant gather --gather "$g" --n "$NS"; done
done; done
