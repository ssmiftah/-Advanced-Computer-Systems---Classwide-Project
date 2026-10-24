#!/usr/bin/env bash
# Shared helpers for the Project 3 scripts. Source this file; do not execute it.
#   safety guard, free-space check, env capture, temperature logger, run_fio wrapper.
set -u

P3_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
COMMON_DIR="$(cd "$P3_DIR/../common" && pwd -P)"
SCRIPTS_DIR="$P3_DIR/scripts"
FIO_JOB="$P3_DIR/configs/base.fio"

QUICK="${QUICK:-0}"      # QUICK=1: tiny sanity defaults (2 GiB file, 4 s reads, 64 MiB per write job, 1 rep)
dflt() { # dflt VAR full_value quick_value : set VAR if unset
  local v="$1"; if [[ -z "${!v:-}" ]]; then if [[ "$QUICK" == 1 ]]; then printf -v "$v" '%s' "$3"; else printf -v "$v" '%s' "$2"; fi; fi
}
dflt TESTFILE_SIZE 32G 2G
dflt RUNTIME 30 4
dflt RAMP 5 1
dflt REPS 3 1
dflt COOLDOWN 20 0
# --- write-wear budget (the target SSD is the user's system drive) -----------------------
# Every job that WRITES (randwrite/write/randrw/rw) is size-bounded instead of time-based:
#   time_based=0, io_size=W_IO_CAP (split over numjobs), runtime=W_RUNTIME acts only as a max.
# fio counts ramp IOs toward io_size, so W_IO_CAP is an exact hard bound per write job+rep.
# No rate caps: the device runs unthrottled; slow points end on W_RUNTIME, fast ones on W_IO_CAP.
# NOTE: io_size/number_ios are IGNORED by fio when time_based=1 (verified: 1M QD32 seq write
# with io_size=1G, time_based, 10 s wrote 58 GiB), which is why write jobs are not time-based.
# W_RAMP defaults to 0: with a byte cap, ramp IOs would eat the cap (a 1M QD32 seq write at 5.3 GB/s
# needs only ~0.8 s for 4 GiB); queue fill-up takes microseconds, so the start-up transient is negligible.
# Measured windows at the default 4 GiB cap: 4K rand QD32 ~3 s (~1M IOs), 1M seq ~0.8 s (4096 IOs),
# 4K QD1 hits W_RUNTIME (10 s, ~0.5M IOs).
dflt W_RUNTIME 10 2       # max measured seconds for a write job
dflt W_RAMP 0 0           # ramp for write jobs (counted in W_IO_CAP; keep << cap / bandwidth)
dflt W_REPS 2 1           # repeats for write jobs (reads use REPS)
dflt W_IO_CAP 4G 64M      # bytes per write job+rep (all numjobs together), ramp included
dflt WRITE_RATE_CAP "" "" # optional fio rate= cap for write jobs (off by default; distorts results)
TESTFILE="${TESTFILE:-$P3_DIR/testfile.dat}"
TESTFILE="$(realpath -m -- "$TESTFILE")"   # absolute + canonical: fio sees exactly the path the guard checked
# QUICK sanity output never lands in the final data/figure dirs
if [[ "$QUICK" == 1 ]]; then _OUT="$P3_DIR/scratch/sanity"; RAW_DIR="${RAW_DIR:-$_OUT/raw}"; PROC_DIR="${PROC_DIR:-$_OUT/processed}"; FIG_DIR="${FIG_DIR:-$_OUT/figures}"; fi
RAW_DIR="${RAW_DIR:-$P3_DIR/data/raw}"
PROC_DIR="${PROC_DIR:-$P3_DIR/data/processed}"
FIG_DIR="${FIG_DIR:-$P3_DIR/figures}"
export RAW_DIR PROC_DIR FIG_DIR
CPUS_SINGLE="${CPUS_SINGLE:-12}"          # cpus_allowed when numjobs == 1
CPUS_MULTI="${CPUS_MULTI:-12-15}"         # cpus_allowed when numjobs  > 1
MIN_FREE_GIB="${MIN_FREE_GIB:-10}"        # keep at least this much free after creating the file
NVME_DEV_NAME="${NVME_DEV_NAME:-nvme0}"
TEMP_PATH="${TEMP_PATH:-/sys/class/nvme/${NVME_DEV_NAME}/hwmon0/temp1_input}"
# Write-bandwidth model for the EXPECTED-volume estimate, calibrated on this drive (KXG80, 2026-10-23,
# 2 GiB file): 4K randwrite QD1 51k IOPS (210 MB/s), 4K randwrite QD32 335k IOPS (1.37 GB/s),
# 128K seqwrite QD1 2.6 GB/s, 1M seqwrite QD32 5.3 GB/s.  bw = min(IOPS_PER_QD*QD*bs, MAX_IOPS*bs, MAX_MBPS)
EST_MAX_W_MBPS="${EST_MAX_W_MBPS:-5300}"
EST_IOPS_PER_QD="${EST_IOPS_PER_QD:-51000}"
EST_MAX_W_IOPS="${EST_MAX_W_IOPS:-335000}"
HARD_MAX_W_MBPS="${HARD_MAX_W_MBPS:-7900}"  # PCIe Gen4 x4 ceiling: worst case for any time-bounded write
YES="${YES:-0}"; DRY="${DRY:-0}"
ESTIMATE_FILE="${ESTIMATE_FILE:-}"

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "[$(date +%H:%M:%S)] $*" >&2; }
to_bytes() { numfmt --from=iec "${1^^}" ; }   # 32G -> bytes (binary units)

common_init() { # common_init "$@" : handles --yes / --estimate
  for a in "$@"; do case "$a" in
    --yes|-y) YES=1;; --estimate) DRY=1;;
    -h|--help) sed -n '2,12p' "$0"; exit 0;;
    *) die "unknown argument: $a";; esac; done
  export YES DRY
}

confirm() { # confirm "message" ; skipped by --yes / YES=1 / DRY
  [[ "$YES" == 1 || "$DRY" == 1 ]] && return 0
  read -r -p "$1 [y/N] " ans; [[ "$ans" == y || "$ans" == Y ]] || die "aborted by user"
}

# ---------------------------------------------------------------- safety guard
# Accept only a regular file (or a not-yet-existing path) named testfile* that
# lives under p3-ssd/. Anything under /dev, a symlink, a directory, or a path
# outside p3-ssd/ is refused.
guard_target() {
  local t="${1:-}"
  [[ -n "$t" ]] || die "empty target"
  case "$t" in /dev/*|/sys/*|/proc/*) die "refusing device/special path: $t";; esac
  local rp; rp="$(realpath -m -- "$t")"
  case "$rp" in /dev/*|/sys/*|/proc/*) die "refusing device/special path: $rp";; esac
  [[ "$rp" == "$P3_DIR"/* ]] || die "target must be inside $P3_DIR (got $rp)"
  [[ "$(basename "$rp")" == testfile* ]] || die "target basename must start with 'testfile' (got $(basename "$rp"))"
  [[ ! -L "$t" ]] || die "target is a symlink: $t"
  # fio splits filename= on ':' (multi-file syntax) -> a path with ':' would make fio open OTHER,
  # relative paths. Also refuse other characters that fio/job-file parsing could mangle.
  case "$rp" in *:*|*\\*|*$'\n'*|*$'\t'*) die "target path contains ':', '\\', newline or tab (fio filename= mis-parses these): $rp";; esac
  if [[ -e "$rp" ]]; then
    [[ -f "$rp" ]] || die "target exists but is not a regular file: $rp"
    # a hard link to some other (user) file would pass every name/location check above
    [[ "$(stat -c %h -- "$rp")" == 1 ]] || die "target has more than one hard link (could alias another file): $rp"
  fi
  return 0
}

# -------------------------------------------------------------- free space
check_free_space() { # check_free_space <size_bytes>
  local need="$1" dir; dir="$(dirname "$TESTFILE")"
  local avail cur=0
  avail=$(df --output=avail -B1 "$dir" | tail -1 | tr -d ' ')
  [[ -f "$TESTFILE" ]] && cur=$(( $(stat -c %b "$TESTFILE") * 512 ))   # space we would reuse
  local extra=$(( need > cur ? need - cur : 0 )) keep=$(( MIN_FREE_GIB * 1024*1024*1024 ))
  if (( avail - extra < keep )); then
    die "free space check failed: avail=$((avail>>30)) GiB, need extra $((extra>>30)) GiB, must keep >= ${MIN_FREE_GIB} GiB free"
  fi
  log "free space OK: avail=$((avail>>30)) GiB, extra needed=$((extra>>30)) GiB, keep>=${MIN_FREE_GIB} GiB"
}

# -------------------------------------------------------------- temperature
read_temp_c() { local t; t=$(cat "$TEMP_PATH" 2>/dev/null) && awk -v t="$t" 'BEGIN{printf "%.1f", t/1000}' || echo "nan"; }
start_templog() { # start_templog <csv>
  local f="$1"; echo "epoch,temp_c" > "$f"
  ( while :; do echo "$(date +%s.%N),$(read_temp_c)" >> "$f"; sleep 1; done ) &
  TEMPLOG_PID=$!
}
stop_templog() { if [[ -n "${TEMPLOG_PID:-}" ]]; then kill "$TEMPLOG_PID" 2>/dev/null; wait "$TEMPLOG_PID" 2>/dev/null; TEMPLOG_PID=; fi; }

# ------------------------------------------------------- environment capture
capture_ssd_info() { # capture_ssd_info <file>
  local f="$1" n="/sys/class/nvme/${NVME_DEV_NAME}"
  {
    echo "# SSD / filesystem info"; echo "date: $(date -Iseconds)"
    echo "model: $(cat $n/model 2>/dev/null | sed 's/ *$//')"
    echo "firmware_rev: $(cat $n/firmware_rev 2>/dev/null | sed 's/ *$//')"
    echo "serial: (omitted)"
    echo "nvme transport/state: $(cat $n/transport 2>/dev/null) $(cat $n/state 2>/dev/null)"
    echo "temp_c: $(read_temp_c)"
    local blk; blk=$(df --output=source "$(dirname "$TESTFILE")" | tail -1)
    echo "test file: $TESTFILE  size=$TESTFILE_SIZE"
    echo "filesystem source: $blk"
    echo "--- df -hT"; df -hT "$(dirname "$TESTFILE")"
    echo "--- findmnt"; findmnt -T "$(dirname "$TESTFILE")" -o TARGET,SOURCE,FSTYPE,OPTIONS 2>/dev/null
    echo "--- block queue"
    for k in scheduler nr_requests rotational logical_block_size physical_block_size read_ahead_kb write_cache; do
      echo "$k: $(cat /sys/block/nvme0n1/queue/$k 2>/dev/null)"; done
    echo "--- nvme smart-log (optional, needs privileges)"
    if command -v nvme >/dev/null; then timeout 5 nvme smart-log "/dev/${NVME_DEV_NAME}" 2>&1 | grep -v -i -E "deprecated|usage|^$|retrieve|either|^\x1b" | head -25 || true; fi
    echo "--- fio"; fio --version
  } > "$f" 2>&1
}

begin_experiment() { # begin_experiment <name> : creates data/raw/<name>, captures env, starts temp logger
  EXP="$1"; EXP_DIR="$RAW_DIR/$EXP"
  [[ "$DRY" == 1 ]] && return 0
  guard_target "$TESTFILE"
  mkdir -p "$EXP_DIR"
  "$COMMON_DIR/env_capture.sh" "$EXP_DIR/env.txt"
  capture_ssd_info "$EXP_DIR/ssd_info.txt"
  start_templog "$EXP_DIR/temp.csv"
  trap 'stop_templog' EXIT INT TERM
  log "experiment '$EXP': output in $EXP_DIR"
}
end_experiment() { stop_templog; [[ "$DRY" == 1 ]] || { [[ "${COOLDOWN:-0}" -gt 0 ]] && sleep "$COOLDOWN"; }; return 0; }

pick_engine() { if fio --enghelp 2>/dev/null | grep -qx '[[:space:]]*io_uring'; then echo io_uring; else echo libaio; fi; }
ENGINE="${ENGINE:-$(pick_engine)}"

require_prepared() {
  guard_target "$TESTFILE"
  [[ -f "$TESTFILE" && -f "$TESTFILE.precond" ]] || die "test file not prepared; run scripts/prepare_testfile.sh first"
  local sz; sz=$(stat -c %s "$TESTFILE")
  (( sz >= $(to_bytes "$TESTFILE_SIZE") )) || die "test file ($sz B) smaller than TESTFILE_SIZE=$TESTFILE_SIZE; re-run prepare_testfile.sh"
}

# ------------------------------------------------------------------ run_fio
# run_fio <label> KEY=VALUE...   (keys: RW RWMIX BS IODEPTH NUMJOBS DIRECT IOENGINE
#   SPAN OFFSET COMPRESS RUNTIME RAMP CPUS BWLOG=1 ENDFSYNC=1 RATE=<fio rate=> ; any
#   other KEY is just recorded as metadata, e.g. SERIES=iodepth)
# Runs REPS repeats, writes $EXP_DIR/<label>_rep<k>.{json,params,err}.
run_fio() {
  local label="$1"; shift
  local -A P=( [RW]=randread [RWMIX]=50 [BS]=4k [IODEPTH]=1 [NUMJOBS]=1 [DIRECT]=1
               [IOENGINE]="$ENGINE" [SPAN]="$TESTFILE_SIZE" [OFFSET]=0 [COMPRESS]=0
               [RUNTIME]="$RUNTIME" [RAMP]="$RAMP" [CPUS]="" [BWLOG]=0 [ENDFSYNC]=0 [RATE]="" [REPS]="$REPS"
               [TIMEBASED]=1 [IOSIZE]="" [INVALIDATE]=1 )
  local -A GIVEN=()
  local kv; for kv in "$@"; do P["${kv%%=*}"]="${kv#*=}"; GIVEN["${kv%%=*}"]=1; done
  [[ -n "${P[CPUS]}" ]] || { if (( P[NUMJOBS] > 1 )); then P[CPUS]="$CPUS_MULTI"; else P[CPUS]="$CPUS_SINGLE"; fi; }
  local wfrac=0
  case "${P[RW]}" in read|randread) wfrac=0;; write|randwrite) wfrac=100;; *) wfrac=$((100 - P[RWMIX]));; esac
  # write-containing jobs: size-bounded (see W_* above); explicit caller values win
  if (( wfrac > 0 )); then
    [[ -n "${GIVEN[RUNTIME]:-}" ]] || P[RUNTIME]="$W_RUNTIME"
    [[ -n "${GIVEN[RAMP]:-}" ]]    || P[RAMP]="$W_RAMP"
    [[ -n "${GIVEN[REPS]:-}" ]]    || P[REPS]="$W_REPS"
    [[ -n "${GIVEN[TIMEBASED]:-}" ]] || P[TIMEBASED]=0
    [[ -n "${P[IOSIZE]}" ]] || P[IOSIZE]="$W_IO_CAP"
    [[ -z "${P[RATE]}" && -n "$WRITE_RATE_CAP" ]] && P[RATE]=",$WRITE_RATE_CAP"
  else
    P[RATE]=""
  fi
  [[ -n "${P[IOSIZE]}" ]] || P[IOSIZE]="${P[SPAN]}"
  # fio's io_size is per job: split the total over numjobs (bytes, multiple of bs)
  local bs_b; bs_b=$(to_bytes "${P[BS]}")
  local iosz_tot_b; iosz_tot_b=$(to_bytes "${P[IOSIZE]}")
  local iosz_job_b=$(( iosz_tot_b / P[NUMJOBS] / bs_b * bs_b ))
  (( iosz_job_b >= bs_b )) || die "IOSIZE too small for numjobs*bs"

  local span_b; span_b=$(to_bytes "${P[SPAN]}")
  (( span_b >= bs_b )) || die "SPAN < BS"
  (( span_b + $(to_bytes "${P[OFFSET]}") <= $(to_bytes "$TESTFILE_SIZE") )) || die "SPAN+OFFSET exceeds TESTFILE_SIZE"

  if [[ "$DRY" == 1 ]]; then
    # columns: exp label seconds expected_GiB worst_GiB
    awk -v e="$EXP" -v l="$label" -v w="$wfrac" -v bs="$bs_b" -v qd="$(( P[IODEPTH] * P[NUMJOBS] ))" \
       -v mx="$EST_MAX_W_MBPS" -v ipq="$EST_IOPS_PER_QD" -v mi="$EST_MAX_W_IOPS" -v hard="$HARD_MAX_W_MBPS" \
       -v rate="${P[RATE]}" -v rt="${P[RUNTIME]}" -v rp="${P[RAMP]}" -v reps="${P[REPS]}" -v tb="${P[TIMEBASED]}" \
       -v cap="$(( iosz_job_b * P[NUMJOBS] ))" \
       'BEGIN{bw=ipq*qd*bs/1e6; if(bw>mx)bw=mx; if(mi*bs/1e6<bw)bw=mi*bs/1e6;
        if(rate!=""){r=rate; sub(/^,/,"",r); v=r+0; if(r ~ /[gG]/)v*=1000; if(v>0&&v<bw)bw=v}
        t=rt+rp; G=1073741824;
        if(w==0){exp_b=0; worst=0; secs=t}
        else if(tb==1){exp_b=bw*1e6*t*w/100; worst=hard*1e6*t; secs=t}
        else {tt=cap/(bw*1e6); if(tt>t)tt=t; exp_b=bw*1e6*tt*w/100; worst=cap; if(hard*1e6*t<worst)worst=hard*1e6*t; secs=tt}
        printf "%s %s %d %.3f %.3f\n", e, l, secs*reps+1*reps, exp_b*reps/G, worst*reps/G}' >> "${ESTIMATE_FILE:-/dev/null}"
    return 0
  fi
  require_prepared

  local k
  for ((k=1; k<=P[REPS]; k++)); do
    local base="$EXP_DIR/${label}_rep${k}"
    local extra=()
    [[ "${P[BWLOG]}" == 1 ]] && extra+=(--write_bw_log="$base" --log_avg_msec=1000)
    [[ "${P[ENDFSYNC]}" == 1 ]] && extra+=(--end_fsync=1)
    [[ -n "${P[RATE]}" ]] && extra+=(--rate="${P[RATE]}")
    local t0 t1 T0 T1
    T0=$(read_temp_c); t0=$(date +%s.%N)
    log "$EXP/$label rep $k/${P[REPS]}  rw=${P[RW]} bs=${P[BS]} qd=${P[IODEPTH]} jobs=${P[NUMJOBS]} span=${P[SPAN]} direct=${P[DIRECT]} eng=${P[IOENGINE]}"
    env FIO_TESTFILE="$TESTFILE" FIO_IOENGINE="${P[IOENGINE]}" FIO_DIRECT="${P[DIRECT]}" FIO_RW="${P[RW]}" \
        FIO_RWMIX="${P[RWMIX]}" FIO_BS="${P[BS]}" FIO_IODEPTH="${P[IODEPTH]}" FIO_NUMJOBS="${P[NUMJOBS]}" \
        FIO_OFFSET="${P[OFFSET]}" FIO_SPAN="${P[SPAN]}" FIO_RUNTIME="${P[RUNTIME]}" FIO_RAMP="${P[RAMP]}" \
        FIO_NAME="$label" FIO_CPUS="${P[CPUS]}" FIO_COMPRESS="${P[COMPRESS]}" \
        FIO_TIMEBASED="${P[TIMEBASED]}" FIO_IOSIZE="$iosz_job_b" FIO_INVALIDATE="${P[INVALIDATE]}" \
      fio "$FIO_JOB" --output-format=json+ --output="$base.json" "${extra[@]}" 2> "$base.err"
    local rc=$?
    t1=$(date +%s.%N); T1=$(read_temp_c)
    { for key in "${!P[@]}"; do echo "$key=${P[$key]}"; done | sort
      echo "exp=$EXP"; echo "label=$label"; echo "rep=$k"; echo "start_epoch=$t0"; echo "end_epoch=$t1"
      echo "temp_start=$T0"; echo "temp_end=$T1"; echo "fio_rc=$rc"; echo "testfile_size=$TESTFILE_SIZE"
      echo "io_size_per_job=$iosz_job_b"; echo "git_rev=$(git -C "$P3_DIR" rev-parse --short HEAD 2>/dev/null || echo none)"
    } > "$base.params"
    (( rc == 0 )) || { log "WARNING: fio rc=$rc (see $base.err)"; sed -n '1,5p' "$base.err" >&2; }
  done
}
