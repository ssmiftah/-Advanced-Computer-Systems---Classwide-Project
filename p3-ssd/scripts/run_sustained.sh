#!/usr/bin/env bash
# Exp 6b: sustained sequential write -> SLC-cache exhaustion / thermal throttling.
# Writes SUST_BS (1M) sequentially at QD SUST_QD (16), wrapping over the test file, until SUST_GIB
# bytes have been written (SIZE-bounded, not time-bounded: io_size=SUST_GIB, time_based=0) or
# SUST_MAX_RUNTIME seconds pass. No ramp, no rate cap. fio logs bandwidth every second
# (write_bw_log, log_avg_msec=1000); NVMe temperature is logged every 1 s.
# Volume: exactly <= SUST_GIB GiB (default 64 GiB, chosen by the user to limit wear; QUICK 1 GiB). Choosing it: a 1 TB TLC client drive's
# dynamic SLC cache scales with FREE NAND (this drive's filesystem is ~88% full, so the cache is
# smaller than on an empty drive, plausibly a few tens of GiB). In a 10 s probe this drive sustained an
# average 5.3 GB/s over ~55 GiB, so the cache (if any drop exists) is likely >= that; 64 GiB may
# not reach it. If no drop is seen, report "SLC cache > SUST_GIB" (a valid lower bound) -- do not just
# keep increasing it.  Env: SUST_GIB, SUST_MAX_RUNTIME (900), SUST_BS, SUST_QD, SUST_RATE (optional cap).
source "$(dirname "$0")/common.sh"; common_init "$@"
dflt SUST_GIB 64 1
dflt SUST_MAX_RUNTIME 900 30
SUST_BS="${SUST_BS:-1m}"; SUST_QD="${SUST_QD:-16}"; SUST_RATE="${SUST_RATE:-}"
extra=(); [[ -n "$SUST_RATE" ]] && extra=("RATE=,${SUST_RATE}")
if [[ "$DRY" != 1 ]]; then
  echo "Sustained write: up to ${SUST_GIB} GiB or ${SUST_MAX_RUNTIME}s, bs=$SUST_BS qd=$SUST_QD, rate=${SUST_RATE:-uncapped}"
  echo "Total write volume: <= ${SUST_GIB} GiB (hard bound, io_size)"
  confirm "Run sustained write test?"
fi
dflt SUST_REPS 1 1
begin_experiment sustained
run_fio "seqwrite_sustained" RW=write BS=$SUST_BS IODEPTH=$SUST_QD RUNTIME=$SUST_MAX_RUNTIME RAMP=0 REPS=$SUST_REPS \
  TIMEBASED=0 IOSIZE="${SUST_GIB}G" BWLOG=1 "${extra[@]}"
end_experiment
