# ECSE 4320/6320 — Class-wide Projects

This is a solo submission. It contains three performance-profiling projects, all measured on one machine.

| Folder | Project | Status | Findings |
|---|---|---|---|
| [`p1-simd/`](p1-simd/) | Project 1: SIMD Advantage Profiling | Final data collected | [p1-simd/FINDINGS.md](p1-simd/FINDINGS.md) |
| [`p2-memory/`](p2-memory/) | Project 2: Cache & Memory Performance Profiling | Final data collected | [p2-memory/FINDINGS.md](p2-memory/FINDINGS.md) |
| [`p3-ssd/`](p3-ssd/) | Project 3: SSD Performance Profiling | Final data collected | [p3-ssd/FINDINGS.md](p3-ssd/FINDINGS.md) |
| [`common/`](common/) | Shared environment capture and benchmark-mode scripts | — | — |
| [`run_everything.sh`](run_everything.sh) | Runs all three projects in sequence | Tested in `--quick` mode for P1 and P2 | — |

Each project folder has its own `README.md` (how to build, run and plot, with per-experiment details),
`FINDINGS.md` (results, analysis, anomalies, limitations, AI-use note) and `REPORT_NOTES.md`
(observations from sanity runs and code review).

## Headline results

**Project 1 (SIMD).**
- AVX-512 speeds up float32 SAXPY, multiply and stencil about **10× in L1**. The gain falls in steps at
  each cache boundary and reaches about **1.0–1.2× at DRAM sizes**: every kernel is memory-bound there
  (DRAM ridge point 6.5 FLOP/B; kernel intensities 0.08–0.6 FLOP/B).
- **Negative example:** GCC reports the floating-point dot product as "vectorized", but it adds the
  results serially, so the speedup is 0.98×. Allowing reassociation gives 27.6×.
- **Misalignment** costs +33% in L1 for AVX-512, exactly where vectors split cache lines.

**Project 2 (Memory).**
- **Latency:** L1 4 cycles, L2 14, L3 47, DRAM 99 ns.
- **One core already reaches 96% of DRAM bandwidth** (55 of 57.6 GB/s), because the DIMMs run at
  3600 MT/s. Adding threads does not raise it.
- **Loaded-latency knee:** about 42 GB/s at about 128 outstanding lines, consistent with Little's Law.
- **Huge pages** halve the cost of random access at 64 MiB–1 GiB footprints by removing page walks.

**Project 3 (SSD).**
- **QD=1 latency:** 4 KiB random read 59.5 µs (p99 82 µs). Writes are acknowledged from cache in
  17.8 µs.
- **4 KiB random reads:** scale almost linearly to QD 32 (400k IOPS), with a knee at **QD 128,
  about 700k IOPS**.
- **Sequential bandwidth:** peaks at 6.3 GB/s, below the PCIe 4.0 ×4 limit.
- **Sustained writes:** fall from 5.4 to about 1.5 GB/s once the roughly 19 GiB SLC cache fills.
- **Misleading setup found in our own first run:** CachyOS's default **Kyber** I/O scheduler cut
  queue-depth results by up to 27×, while Little's Law still appeared to hold perfectly. The final
  data uses no scheduler.

## Machine

| | |
|---|---|
| CPU | AMD Ryzen 9 9950X (Zen 5), 16 cores / 32 threads, AVX-512, 2 CCDs |
| Caches | L1d 48 KiB and L2 1 MiB per core; L3 32 MiB per CCD |
| Memory | 4 × 16 GiB DDR5-4800 running at 3600 MT/s, dual channel; 1 NUMA node |
| SSD | KIOXIA KXG80ZNV1T02, 1 TB NVMe (system drive) |
| OS | CachyOS, Linux 7.3.0; GCC 16.2.1, Clang 23.1.3, perf 7.2.11, fio 3.42 |

Every run's raw-data folder contains an `env.txt` with the full environment captured at run time: CPU,
governor, boost, SMT, THP, memory modules, tool versions and load.

## Reproducing

### 1. One-time setup
```
sudo pacman -S --needed perf fio nvme-cli   # system tools (Arch/CachyOS)
uv sync                                     # Python env from uv.lock (or use venv + pip, see below)
```

**Ubuntu / Debian-based alternative** (for Ubuntu 24.04 or newer), system tools:
```
sudo apt update
sudo apt install -y build-essential gcc-14 clang fio nvme-cli inxi dmidecode util-linux      linux-tools-common linux-tools-generic "linux-tools-$(uname -r)"   # perf + cpupower
export CC=gcc-14                                                         # -march=znver5 needs GCC >= 14 (24.04 defaults to GCC 13)
```
- `export CC=gcc-14` applies only to the current shell. Run it in the same shell as the build and run
  commands below, or add it to `~/.bashrc`. On Ubuntu 25.04 and later the default `gcc` is already 14
  or newer, so you can skip it.
- If `perf` warns that it is not built for the running kernel (common with HWE or custom kernels),
  install the matching package with `sudo apt install linux-tools-$(uname -r)`. On cloud kernels, use
  `linux-tools-aws`, `linux-tools-azure` and so on.
- Check the tools with `gcc-14 --version; perf --version; cpupower --version; fio --version`.

#### Python environment: venv + pip (no uv needed)

uv is **not required**. All scripts run Python through [`common/pyrun.sh`](common/pyrun.sh), which picks
the first of these that exists:

1. `$ACS_PYTHON`, if you set it;
2. the active venv;
3. `.venv/` at the repo root;
4. `uv run`, only if uv is installed;
5. `python3` on PATH.

The project needs Python 3.13 or newer.
```
# Ubuntu 24.04 ships Python 3.12, so get 3.13 first (Ubuntu 25.04+ already has it):
sudo apt install -y software-properties-common && sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.13 python3.13-venv
# Arch/CachyOS: sudo pacman -S --needed python   (already 3.13+)

python3.13 -m venv .venv                 # create the venv at the repo root; scripts find it automatically
source .venv/bin/activate                # optional for the scripts; needed to call python/pip directly
python -m pip install --upgrade pip
python -m pip install "numpy>=2.5.4" "pandas>=3.1.0" "matplotlib>=3.11.2" "scipy>=1.18.1"
common/pyrun.sh --check                  # shows which Python the scripts will use and checks the packages
```
- The venv must be named `.venv` and sit at the repo root to be found without activating it. A venv
  elsewhere works when it is activated, or with `export ACS_PYTHON=/path/to/venv/bin/python`.
- `run_everything.sh` runs `common/pyrun.sh --check` first and stops with a clear message if a package
  is missing.
- To run a single Python step by hand: `common/pyrun.sh p1-simd/scripts/process.py --raw ... --out ...`,
  or just `python p1-simd/scripts/process.py ...` with the venv activated.
- To leave the venv: `deactivate`. To remove it: `rm -rf .venv`.

#### Optional: uv instead of pip

Use uv to install the exact versions pinned in `uv.lock`:
```
curl -LsSf https://astral.sh/uv/install.sh | sh    # install uv (or: sudo snap install astral-uv --classic)
source ~/.local/bin/env                            # put uv on PATH in this shell
uv sync                                            # creates .venv from uv.lock; fetches Python 3.13 if needed
```
To get the same pinned versions with pip, export them once on any machine that has uv, then install
them with pip:
```
uv export --format requirements-txt --no-hashes --no-emit-project > requirements.txt
python -m pip install -r requirements.txt
```

### 2. Quiet the machine (system-wide, needs sudo)
```
sudo common/bench_mode.sh on          # performance governor, perf counters readable,
                                      # NVMe I/O scheduler set to "none"
                                      # add --no-boost to disable turbo
```
Run the projects **one at a time** on an otherwise idle machine. Running them together distorts the
memory and L3 results.

**Ubuntu notes:** `bench_mode.sh` works unchanged on Ubuntu. It needs `cpupower`, which comes from the
`linux-tools-*` packages above. Ubuntu already uses the `none` scheduler for NVMe drives, so that step
changes nothing there. To check the settings, or to set them by hand without the script:
```
cat /sys/block/nvme0n1/queue/scheduler                      # expect: [none] mq-deadline ...
cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor
sudo cpupower frequency-set -g performance                  # manual equivalent of the governor step
sudo sysctl kernel.perf_event_paranoid=-1                   # manual equivalent of the perf step
```
If you lose `/tmp/acs_bench_mode_saved` (for example after a reboot), `bench_mode.sh off` falls back to
`kyber`. On Ubuntu, put the scheduler back with
`echo none | sudo tee /sys/block/nvme0n1/queue/scheduler` (a reboot also restores all defaults).

### 3. Run everything with one command
```
./run_everything.sh --quick     # ~3 min smoke test of all three; sanity folders only
./run_everything.sh             # full collection, ~3.3 h, P1 → P2 → P3; asks before SSD writes
./run_everything.sh --only p1,p2
```
`run_everything.sh` checks that the machine is in bench mode, moves any existing final data to
`<dir>.prev-<timestamp>` (it never deletes data), runs each project's build, experiments, processing and
plots, deletes the SSD test file at the end, and logs everything to `logs/`.
[REQUIREMENTS_CHECKLIST.md](REQUIREMENTS_CHECKLIST.md) maps every assignment requirement to the file
that meets it.

### 3b. Or run each project separately

| Project | Command (from repo root) | Approx. time | Output |
|---|---|---|---|
| P1 | `OUT_ROOT=$PWD/p1-simd/data/raw/final p1-simd/scripts/run_all.sh` | 45 min | `p1-simd/{data/raw,data/processed,figures}/final/` |
| P2 | `cd p2-memory && make && scripts/run_all.sh`, then `process.py` and the `plot_*.py` scripts (see `p2-memory/README.md`) | 30 min | `p2-memory/{data/raw,data/processed,figures}/final/` |
| P3 | `bash p3-ssd/scripts/run_all.sh` then `bash p3-ssd/scripts/plot_all.sh` | 2 h | `p3-ssd/{data,figures}/` (`data/kyber/`, `figures/kyber/` hold the invalid first run kept as pitfall evidence) |

All three support `QUICK=1` for a smoke test of under a minute that writes to separate sanity folders.

On Ubuntu, the commands in sections 3 and 3b are the same. On Ubuntu 24.04, run `export CC=gcc-14`
first so both Makefiles build with GCC 14. For P2 you can also pass it directly:
`cd p2-memory && make CC=gcc-14`.

### 4. Restore the machine
```
sudo common/bench_mode.sh off
bash p3-ssd/scripts/cleanup.sh        # delete the 32 GiB SSD test file
```

## SSD safety (Project 3)

- **No raw devices:** the SSD is the system drive, so Project 3 never touches a raw device or partition.
  All I/O goes to a regular `p3-ssd/testfile*`, and a guard in `p3-ssd/scripts/common.sh` rejects any
  other target, including `/dev` paths, symlinks, hard links and paths containing `:`.
- **Write volume:** every write job is bounded by bytes, not time. A full run writes about **351 GiB**,
  with a hard upper bound of **384 GiB**. That includes a 64 GiB sustained-write test. To rerun
  experiments without rebuilding the test file, use `SKIP_PREPARE=1 EXPS="run_qd_sweep ..."`.
- **Confirmation:** `run_all.sh` prints the estimate and asks for confirmation before writing.

## Repository layout (per project)

```
pN-*/
  src/ or configs/     benchmark sources / fio job files
  scripts/             run_*.sh (one per experiment), run_all.sh, process/parse + plot_*.py
  data/raw/final/      raw measurements + env.txt per experiment
  data/processed/final summary tables (median, IQR, derived metrics)
  figures/final/       PNG + PDF figures
  reports/             (P1) compiler vectorization reports, disassembly summaries
  README.md            how to run; experiment definitions
  FINDINGS.md          results and analysis
```

## AI use

- **Who wrote what:** Claude Code (Anthropic) wrote the code, scripts and findings drafts, at the
  student's direction. Claude Sonnet agents wrote each project's code; separate Claude Opus agents then
  reviewed and fixed it.
- **What the reviews changed:** they fixed error-bar methodology, counter selection, Little's Law
  analysis, safety guards and SSD write volume.
- **What inspecting the results changed:** the Kyber scheduler problem was caught by inspecting the
  first SSD results, confirmed with read-only tests, and the affected experiments were rerun.
- **Where to find the details:** each project's `FINDINGS.md`.
- **Responsibility:** I am responsible for understanding and validating all submitted code,
  measurements and claims.
