#!/usr/bin/env bash
# Experiment 6: vectorization verification: builds, regenerates reports/ (opt-info, objdump, summary).
source "$(dirname "$0")/common.sh"
cd "$ROOT" && make -B vec-reports 2>&1 | tail -3
"$COMMON/env_capture.sh" "$ROOT/reports/env.txt"
echo "(optional, clang remarks: make clang-reports)"
