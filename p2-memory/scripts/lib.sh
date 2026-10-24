# Shared helpers for the run_*.sh scripts. Source, do not execute.
#
# Environment knobs (all optional):
#   QUICK=1       tiny sanity configuration; output goes to data/raw/sanity
#   OUT=DIR       output root (default data/raw/final, or data/raw/sanity if QUICK=1)
#   CPU=N         CPU for single-thread runs                     (default 4)
#   THREAD_CPUS   CPU list for multi-thread runs (first one is the latency
#                 probe in loaded-latency runs). Default: 4,5,6,7,8,9,10,11
#                 (4 cores on CCD0 + 4 on CCD1, one thread per physical core; avoids
#                 cpus 0-3 (desktop/other jobs) and 12-13); QUICK: 4,5,6,7.
#   REPS_LAT / REPS_BW / SECS   repetitions and per-rep seconds
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$ROOT/bin"
COMMON="$ROOT/../common"
QUICK="${QUICK:-0}"
CPU="${CPU:-4}"
if [[ "$QUICK" == 1 ]]; then
  OUT="${OUT:-$ROOT/data/raw/sanity}"
  THREAD_CPUS="${THREAD_CPUS:-4,5,6,7}"
  REPS_LAT="${REPS_LAT:-3}"; REPS_BW="${REPS_BW:-2}"; SECS="${SECS:-0.15}"
else
  OUT="${OUT:-$ROOT/data/raw/final}"
  THREAD_CPUS="${THREAD_CPUS:-4,5,6,7,8,9,10,11}"
  REPS_LAT="${REPS_LAT:-11}"; REPS_BW="${REPS_BW:-5}"; SECS="${SECS:-0.5}"
fi
IFS=',' read -r -a TCPU <<< "$THREAD_CPUS"
NT=${#TCPU[@]}                       # max thread count
KiB=1024; MiB=$((1024*1024)); GiB=$((1024*1024*1024))

[[ -x "$BIN/bandwidth" ]] || make -C "$ROOT" >/dev/null

# mkout NAME -> creates $OUT/NAME, saves environment, sets $D
mkout() {
  D="$OUT/$1"
  # append() adds rows to existing CSVs, so a re-run would silently mix two runs (and two
  # env.txt states). Refuse instead; move the old directory away or set OUT=... .
  if compgen -G "$D/*.csv" > /dev/null; then
    echo "error: $D already contains CSVs; move it away (raw data is never overwritten) or set OUT" >&2
    exit 1
  fi
  mkdir -p "$D"
  "$COMMON/env_capture.sh" "$D/env.txt"
  # DIMM population and configured speed decide the DRAM bandwidth ceiling (here 4 x DDR5-4800
  # DIMMs, 2 per channel, running at 3600 MT/s -> 57.6 GB/s peak); inxi reads it without root.
  { echo; echo "## DRAM modules (inxi -m)"; inxi -m -xx -c0 2>/dev/null || echo "inxi unavailable: run sudo dmidecode -t memory"; } >> "$D/env.txt"
  { echo "script: $1"; echo "QUICK=$QUICK CPU=$CPU THREAD_CPUS=$THREAD_CPUS REPS_LAT=$REPS_LAT REPS_BW=$REPS_BW SECS=$SECS"; } >> "$D/env.txt"
  echo "== $1 -> $D" >&2
}

# append FILE CMD... : append CMD's stdout rows to FILE, adding --header the first time
append() {
  local f="$1"; shift
  if [[ -s "$f" ]]; then "$@" >> "$f"; else "$@" --header >> "$f"; fi
}

# cpus_n N -> comma list of the first N entries of THREAD_CPUS
cpus_n() { local IFS=,; echo "${TCPU[*]:0:$1}"; }

# thread counts to sweep (capped by NT)
thread_counts() {
  local out=() t
  for t in 1 2 4 8 16; do (( t <= NT )) && out+=("$t"); done
  [[ " ${out[*]} " == *" $NT "* ]] || out+=("$NT")
  echo "${out[*]}"
}

# sizes_octave LO HI : geometric sweep with 2 points per octave (x1, x1.5)
sizes_octave() {
  local s=$1 hi=$2 h
  while (( s <= hi )); do
    echo "$s"; h=$(( s * 3 / 2 )); (( h <= hi )) && echo "$h"; s=$(( s * 2 ))
  done
}

# perf_run LABEL EVENTS PROG... : run PROG (which must accept --ctl/--ack) under
# perf stat so counters cover only its timed region. stdout of PROG -> $PERF_PROG_OUT,
# perf CSV -> $PERF_OUT.
perf_run() {
  local events="$1"; shift
  local tmp; tmp="$(mktemp -d)"
  mkfifo "$tmp/ctl" "$tmp/ack"
  perf stat -x, -D -1 --control "fifo:$tmp/ctl,$tmp/ack" -e "$events" -o "$PERF_OUT" -- \
      "$@" --ctl "$tmp/ctl" --ack "$tmp/ack" > "$PERF_PROG_OUT"
  rm -rf "$tmp"
}

# csv_add FILE SRC [TAG] : append SRC (header + rows) to FILE, keeping a single header;
# with TAG, add an "evset" column holding TAG.
csv_add() {
  local f="$1" src="$2" tag="${3:-}"
  if [[ ! -s "$f" ]]; then
    if [[ -n "$tag" ]]; then head -1 "$src" | sed 's/$/,evset/' > "$f"; else head -1 "$src" > "$f"; fi
  fi
  if [[ -n "$tag" ]]; then tail -n +2 "$src" | sed "s/\$/,$tag/" >> "$f"; else tail -n +2 "$src" >> "$f"; fi
}
