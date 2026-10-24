#!/usr/bin/env bash
# Delete the test file (and its precondition marker). Raw data is kept.
source "$(dirname "$0")/common.sh"
guard_target "$TESTFILE"
rm -fv "$TESTFILE" "$TESTFILE.precond"
