#!/usr/bin/env bash
# common.sh - sourced by run_*.sh.  Environment knobs (all optional):
#   OUT_ROOT  raw-data root           (default p1-simd/data/raw; sanity runs use data/raw/sanity)
#   CPU       core to pin to          (default 3)
#   SAMPLES   timed samples/config    (default 15)
#   MINMS     min ms per sample       (default 8)
#   REPEATS   independent process invocations per config (default 3; QUICK: 1).  Each uses a
#             different --seed (data + allocation); between-process variation at DRAM sizes was
#             measured at 5-15% (page placement / shared memory controller), far larger than the
#             within-process IQR, so error bars must pool several invocations.
#   QUICK=1   tiny config for smoke tests (few sizes, few samples)
#   BUILDS    override build list
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMON="$(cd "$ROOT/../common" && pwd)"
BIN="$ROOT/bin"
OUT_ROOT="${OUT_ROOT:-$ROOT/data/raw}"
CPU="${CPU:-3}"
QUICK="${QUICK:-0}"
if [ "$QUICK" = 1 ]; then SAMPLES="${SAMPLES:-3}"; MINMS="${MINMS:-2}"; REPEATS="${REPEATS:-1}"
else SAMPLES="${SAMPLES:-15}"; MINMS="${MINMS:-8}"; REPEATS="${REPEATS:-3}"; fi
ALL_BUILDS="scalar scalar_znver5 sse avx2 znver5 sse_fm avx2_fm znver5_fm"
[ "$QUICK" = 1 ] && ALL_BUILDS="scalar sse avx2 znver5 znver5_fm"

# init_exp NAME -> sets OUTDIR, CSV; records environment + build flags next to the data
init_exp() {
    EXP="$1"; OUTDIR="$OUT_ROOT/$EXP"; mkdir -p "$OUTDIR"
    CSV="$OUTDIR/$EXP.csv"
    "$BIN/simd_scalar" --header-only > "$CSV"
    "$COMMON/env_capture.sh" "$OUTDIR/env.txt"
    { echo; echo "## run parameters"; echo "pinned cpu: $CPU  samples: $SAMPLES  min-ms: $MINMS  repeats: $REPEATS  quick: $QUICK";
      echo "script: $0"; echo "## compiler/flags (reports/flags.txt)"; cat "$ROOT/reports/flags.txt" 2>/dev/null; } >> "$OUTDIR/env.txt"
    echo "[$EXP] -> $CSV"
}

# bench BUILD ARGS... : append rows (pinned, no repeated header); REPEATS separate processes,
# seeds 12345, 12346, ... (seed is recorded in the csv)
bench() {
    local b="$1"; shift
    for ((r = 0; r < REPEATS; r++)); do
        taskset -c "$CPU" "$BIN/simd_$b" --exp "$EXP" --samples "$SAMPLES" --min-ms "$MINMS" --seed $((12345 + r)) --no-header "$@" >> "$CSV"
    done
}

# fm builds only differ for FP reductions, so only run them for dot (kernel $1)
skip_build() { # skip_build BUILD KERNEL TYPE
    case "$1" in *_fm) [ "$2" = dot ] && [ "$3" != i32 ] && return 1 || return 0;; esac
    return 1
}
