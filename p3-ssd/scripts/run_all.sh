#!/usr/bin/env bash
# Run the whole Project 3 pipeline: prepare -> exp1..7 (exp 4 is parsed right away so exp 5 uses its knee).
# Prints the estimated duration, EXPECTED write volume (bandwidth model calibrated on this drive, see
# common.sh EST_*) and the HARD worst-case write bound (sum of the per-job io_size caps); asks for
# confirmation unless --yes.  Flags: --yes, --estimate (print estimate only).
# Env: see common.sh (QUICK=1 for a tiny sanity run into p3-ssd/scratch/sanity/).
#   EXPS="run_bs_sweep run_qd_sweep ..."  run only these experiments (default: all)
#   SKIP_PREPARE=1                        reuse the existing, already-preconditioned test file
source "$(dirname "$0")/common.sh"; common_init "$@"
if [[ -n "${EXPS:-}" ]]; then read -r -a EXPS <<< "$EXPS"
else EXPS=(run_qd1 run_bs_sweep run_rwmix run_qd_sweep run_tail run_workingset run_sustained run_misleading); fi
PREP=(prepare_testfile); [[ "${SKIP_PREPARE:-0}" == 1 ]] && PREP=()
est=$(mktemp); export ESTIMATE_FILE="$est"
for s in "${PREP[@]}" "${EXPS[@]}"; do DRY=1 bash "$SCRIPTS_DIR/${s%.sh}.sh" --estimate; done
unset ESTIMATE_FILE
awk -v cd="$COOLDOWN" -v n=${#EXPS[@]} '
  {secs+=$3; e+=$4; w+=$5; S[$1]+=$3; E[$1]+=$4; W[$1]+=$5; if(!($1 in O)){O[$1]=++k; N[k]=$1}}
  END{printf "  %-12s %8s %12s %12s\n", "experiment", "time", "expected", "worst-case" > "/dev/stderr";
      for(i=1;i<=k;i++){x=N[i]; printf "  %-12s %7.0fs %9.1f GiB %9.1f GiB\n", x, S[x], E[x], W[x] > "/dev/stderr"}
      secs+=cd*n; printf "ESTIMATE: duration ~ %.1f h; writes: expected ~ %.0f GiB, HARD worst case <= %.0f GiB (incl. test-file fill)\n", secs/3600, e, w}' "$est"
echo "(expected: write-bw model calibrated on this drive -- EST_MAX_W_MBPS=$EST_MAX_W_MBPS, EST_MAX_W_IOPS=$EST_MAX_W_IOPS, EST_IOPS_PER_QD=$EST_IOPS_PER_QD;"
echo " worst case: every write job runs until its io_size cap W_IO_CAP=$W_IO_CAP x W_REPS=$W_REPS; sustained SUST_GIB; the buffered-write demo can add page-cache writeback <= its cap)"
rm -f "$est"
[[ "$DRY" == 1 ]] && exit 0
confirm "Run everything against $TESTFILE ($TESTFILE_SIZE)?"
export YES=1
if [[ ${#PREP[@]} -gt 0 ]]; then bash "$SCRIPTS_DIR/prepare_testfile.sh" --yes || exit 1
else guard_target "$TESTFILE" || exit 1; [[ -s "$TESTFILE" ]] || { echo "SKIP_PREPARE=1 but no test file" >&2; exit 1; }; fi
w0=$(awk '{print $7}' /sys/block/nvme0n1/stat 2>/dev/null || echo 0)
for s in "${EXPS[@]}"; do
  bash "$SCRIPTS_DIR/$s.sh" --yes
  if [[ $s == run_qd_sweep ]]; then   # knee for exp 5
    rm -f "$PROC_DIR/knee.txt"
    (cd "$P3_DIR/.." && bash common/pyrun.sh p3-ssd/scripts/parse_fio.py && bash common/pyrun.sh p3-ssd/scripts/plot_qd_sweep.py) \
      || log "WARNING: could not compute knee; run_tail uses its default"
  fi
done
w1=$(awk '{print $7}' /sys/block/nvme0n1/stat 2>/dev/null || echo 0)
echo "Device-level writes during experiments (all processes, from /sys/block/nvme0n1/stat): $(( (w1 - w0) * 512 >> 30 )) GiB"
echo "Done. Next: bash p3-ssd/scripts/plot_all.sh (from the repo root; honours RAW_DIR/PROC_DIR/FIG_DIR, QUICK=1)"
