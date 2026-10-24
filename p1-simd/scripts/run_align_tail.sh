#!/usr/bin/env bash
# Experiment 3: alignment (byte offsets from a 64 B line) and tail (n mod vector width) study.
#  - alignment: offsets applied to x,y(,z) together ("both") or to x only; sizes in L1 / L2 / DRAM
#  - tail: n = multiples of 64 (no remainder in any ISA) vs n with remainders, at L1 size and tiny n
source "$(dirname "$0")/common.sh"; init_exp align_tail
if [ "$QUICK" = 1 ]; then OFFS="0 4 32"; WS="16"; TAILN="1024,1027,64,65"; TYPES="f32"; KERNELS="saxpy"
else OFFS="0 4 8 16 32 48"; WS="16,512,262144"; TYPES="f32 f64"
  TAILN="16,17,31,32,33,63,64,65,1024,1025,1026,1027,1028,1031,1032,1039,1040,1041,4096,4097,4099,4103,4111,4113"
  KERNELS="saxpy dot mul stencil"; fi
BS="${BUILDS:-scalar sse avx2 znver5 znver5_fm}"
for k in $KERNELS; do for b in $BS; do
  skip_build "$b" "$k" f32 && continue
  for t in $TYPES; do
    for o in $OFFS; do
      bench "$b" --kernel "$k" --type "$t" --ws-kib "$WS" --offx "$o" --offy "$o" --offz "$o"
      [ "$o" != 0 ] && bench "$b" --kernel "$k" --type "$t" --ws-kib "$WS" --offx "$o" --offy 0 --offz 0
    done
    bench "$b" --kernel "$k" --type "$t" --n "$TAILN"
  done
done; done
