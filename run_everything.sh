#!/usr/bin/env bash
# Run all three class-wide projects in sequence: build -> experiments -> processing -> figures.
#
#   ./run_everything.sh --quick            # smoke test (~2-3 min, tiny configs, sanity output dirs,
#                                          #   writes ~4 GiB to the SSD test file)
#   ./run_everything.sh                    # full final collection (~3.3 h; P3 writes ~351 GiB)
#   ./run_everything.sh --only p1,p2       # subset (p1, p2, p3 in any combination)
#   ./run_everything.sh --yes              # skip confirmations (including P3's write-volume prompt)
#   ./run_everything.sh --force            # run even if the machine is not in bench mode
#
# Before a full run:   sudo common/bench_mode.sh on     (governor, perf counters, NVMe scheduler)
# After it:            sudo common/bench_mode.sh off
#
# Existing final data is never overwritten or deleted: it is moved to <dir>.prev-<timestamp>.
# Run the projects on an otherwise idle machine; they are run one at a time on purpose.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
TS="$(date +%Y%m%d-%H%M%S)"
QUICK=0 YES=0 FORCE=0 ONLY="p1,p2,p3"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick) QUICK=1 ;; --yes) YES=1 ;; --force) FORCE=1 ;;
    --only) ONLY="$2"; shift ;;
    -h|--help) sed -n 2,16p "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac; shift
done
export QUICK
mkdir -p logs; LOG="$ROOT/logs/run_everything_$TS.log"
exec > >(tee -a "$LOG") 2>&1
say() { printf '\n[%s] %s\n' "$(date +%T)" "$*"; }
want() { [[ ",$ONLY," == *",$1,"* ]]; }
die() { say "ERROR: $*"; exit 1; }
# Move a directory aside (never delete) if it exists and is non-empty.
stash() { [[ -d "$1" && -n "$(ls -A "$1" 2>/dev/null)" ]] && { mv "$1" "$1.prev-$TS"; say "moved old $1 -> $1.prev-$TS"; }; return 0; }

# ---------- preflight ----------
say "preflight (QUICK=$QUICK, projects: $ONLY, log: $LOG)"
for t in gcc make perf fio taskset; do command -v "$t" >/dev/null || die "missing tool: $t"; done
bash common/pyrun.sh --check || die "Python environment not ready (see README, section 1: venv + pip, or uv)"
gov=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor)
par=$(cat /proc/sys/kernel/perf_event_paranoid)
sch=$(sed -E 's/.*\[(.*)\].*/\1/' /sys/block/nvme0n1/queue/scheduler 2>/dev/null || echo unknown)
echo "governor=$gov perf_event_paranoid=$par nvme0n1_scheduler=$sch"
problems=()
[[ "$gov" == performance ]] || problems+=("CPU governor is '$gov' (want performance)")
[[ "$par" -le 1 ]] || problems+=("perf_event_paranoid=$par: P2 cache/TLB counters may fail (want <= 1)")
want p3 && [[ "$sch" != none ]] && problems+=("NVMe scheduler is '$sch': it distorts P3 queue-depth results (want none)")
if [[ ${#problems[@]} -gt 0 ]]; then
  printf '  - %s\n' "${problems[@]}"
  if [[ $QUICK == 0 && $FORCE == 0 ]]; then die "machine not in bench mode; run 'sudo common/bench_mode.sh on' or pass --force"; fi
  say "continuing anyway (quick mode or --force); results are not valid as final data"
fi
if [[ $QUICK == 0 && $YES == 0 ]]; then
  read -r -p "Full run of [$ONLY] (~3.3 h total; P3 writes ~351 GiB to the SSD). Continue? [y/N] " a
  [[ "$a" == [yY]* ]] || exit 0
fi
"$ROOT/common/env_capture.sh" "$ROOT/logs/env_$TS.txt"
status=()

# ---------- Project 1: SIMD ----------
if want p1; then
  say "P1 SIMD: start"
  if [[ $QUICK == 1 ]]; then out="$ROOT/p1-simd/data/raw/sanity/run_$TS"
  else out="$ROOT/p1-simd/data/raw/final"; stash "$out"; stash "$ROOT/p1-simd/data/processed/final"; stash "$ROOT/p1-simd/figures/final"; fi
  if OUT_ROOT="$out" p1-simd/scripts/run_all.sh; then status+=("P1 ok"); else status+=("P1 FAILED"); fi
fi

# ---------- Project 2: cache & memory ----------
if want p2; then
  say "P2 memory: start"
  if [[ $QUICK == 1 ]]; then tag="sanity/run_$TS"; else tag="final"; for d in raw processed; do stash "$ROOT/p2-memory/data/$d/final"; done; stash "$ROOT/p2-memory/figures/final"; fi
  ok=1
  ( cd p2-memory && make -s && OUT="$ROOT/p2-memory/data/raw/$tag" scripts/run_all.sh ) || ok=0
  if [[ $ok == 1 ]]; then
    bash common/pyrun.sh p2-memory/scripts/process.py "p2-memory/data/raw/$tag" "p2-memory/data/processed/$tag" || ok=0
    for p in latency bandwidth intensity kernel pitfall; do
      bash common/pyrun.sh "p2-memory/scripts/plot_$p.py" --in "p2-memory/data/processed/$tag" --out "p2-memory/figures/$tag" || { echo "plot_$p failed"; ok=0; }
    done
  fi
  [[ $ok == 1 ]] && status+=("P2 ok") || status+=("P2 FAILED")
fi

# ---------- Project 3: SSD ----------
if want p3; then
  say "P3 SSD: start"
  [[ $QUICK == 0 ]] && { stash "$ROOT/p3-ssd/data/raw"; stash "$ROOT/p3-ssd/data/processed"; }
  yes=(); [[ $YES == 1 || $QUICK == 1 ]] && yes=(--yes)
  ok=1
  bash p3-ssd/scripts/run_all.sh "${yes[@]}" || ok=0
  [[ $ok == 1 ]] && { bash p3-ssd/scripts/plot_all.sh || ok=0; }
  bash p3-ssd/scripts/cleanup.sh || true          # always delete the test file
  [[ $QUICK == 1 ]] && rm -rf p3-ssd/scratch
  [[ $ok == 1 ]] && status+=("P3 ok") || status+=("P3 FAILED")
fi

say "summary: ${status[*]:-nothing run}"
[[ $QUICK == 1 ]] && echo "Quick-mode output went to sanity folders; final data was not touched."
echo "Log: $LOG"
[[ "${status[*]:-}" != *FAILED* ]]
