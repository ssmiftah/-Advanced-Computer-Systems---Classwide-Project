# Assignment Requirements Checklist

Each requirement from *ECSE 4320/6320 Class-wide Projects* is listed with where it is met in this
repository. Section numbers (§) refer to each project's `FINDINGS.md`.

## Common requirements (all projects)

| Requirement | P1 SIMD | P2 Memory | P3 SSD |
|---|---|---|---|
| AI-use note | `p1-simd/FINDINGS.md` §13 | `p2-memory/FINDINGS.md` §12 | `p3-ssd/FINDINGS.md` §12 |
| Source code | `p1-simd/src/` | `p2-memory/src/` | `p3-ssd/configs/`, `p3-ssd/scripts/` |
| Build scripts | `p1-simd/Makefile` | `p2-memory/Makefile` | — (fio jobs; no build needed) |
| Run scripts | `p1-simd/scripts/run_*.sh` | `p2-memory/scripts/run_*.sh` | `p3-ssd/scripts/run_*.sh` |
| One script for everything | `run_everything.sh` (repo root) | ← | ← |
| Plotting scripts | `p1-simd/scripts/plot_*.py` | `p2-memory/scripts/plot_*.py` | `p3-ssd/scripts/plot_*.py` |
| Raw data | `p1-simd/data/raw/final/` | `p2-memory/data/raw/final/` | `p3-ssd/data/raw/` |
| Processed data | `p1-simd/data/processed/final/` | `p2-memory/data/processed/final/` | `p3-ssd/data/processed/` |
| README | `p1-simd/README.md` | `p2-memory/README.md` | `p3-ssd/README.md` |
| Pre-experiment hypothesis | §2 | §2 | §2 |
| Correctness validation | §1 (scalar reference, 480-config sweep) | §3 (Sattolo single cycle; cycles from measured clock), §6 (write-allocate checked with counters) | §1 (non-sparse precondition, incompressible-data check), §6 (Little's Law consistency) |
| Measurement discipline (hardware, OS, tool versions, governor, SMT, pinning, repetitions, error bars) | §1; `env.txt` in every raw-data folder | §1; `env.txt` (also lists DIMMs) | §1; `env.txt`, `ssd_info.txt`, `temp.csv`, `.params` per run |
| Negative / failure case | §10 (dot product "vectorized" but 0.98×; SAXPY at DRAM 1.02×) | §5 (DRAM bandwidth does not scale with threads), §9 | §9 (Kyber scheduler, buffered I/O, wrong effective QD) |
| Honest anomalies | §11 | §10 | §10 |
| Python environment | `pyproject.toml`, `uv.lock`, `common/pyrun.sh` (venv + pip or uv) | ← | ← |
| Environment capture / bench mode | `common/env_capture.sh`, `common/bench_mode.sh` | ← | ← |

## Project 1 — SIMD Advantage Profiling

| Required item | Where |
|---|---|
| ≥ 3 kernels | All 4: SAXPY, dot, multiply, 3-point stencil (`src/kernels_impl.inc`) |
| float32 vs float64 (optional int32) | §8; `figures/final/dtype_*.png` |
| Alignment and tail handling | §6; `figures/final/align_*.png`, `tail_*.png` |
| Stride / gather | §7; `figures/final/stride_*.png` |
| Working-set sweep L1 → DRAM | §4–5; `figures/final/locality_*.png`, `speedup_*.png` |
| Scalar vs auto-vectorized vs widest ISA | §1 build table; 10 builds in `Makefile`, flags in `reports/flags.txt` |
| Vectorization verification | §3; `reports/vec_summary.md`, `reports/vec_snippets.md`, `reports/*.vec-*.txt` |
| Roofline with measured bandwidth and peak | §9; `figures/final/roofline.png` |
| Negative example, verified | §10 |
| Runtime, GFLOP/s, GiB/s, cycles/element | All summary CSVs in `data/processed/final/` |

## Project 2 — Cache & Memory Performance Profiling

| Required item | Where |
|---|---|
| Zero-queue latency per level (with cycles) | §3; `data/processed/final/latency/zero_queue_table.csv` |
| Pattern / granularity sweep (latency and bandwidth) | §4; `figures/final/latency_pattern_stride.png`, `bandwidth_pattern_stride.png` |
| Read/write mix: 100R, 100W, 70/30, 50/50 | §6; `figures/final/bandwidth_rwmix.png`, `loaded_latency_rwmix.png` |
| Intensity sweep, knee, Little's Law | §7; `figures/final/intensity_mlp.png`, `intensity_loaded_latency.png` |
| Working-set sweep with transitions annotated | §3; `figures/final/latency_working_set.png` |
| Cache-miss impact with perf counters | §8; `figures/final/kernel_cache_miss.png` |
| TLB-miss impact, 4 KiB vs huge pages | §8; `figures/final/tlb_miss_impact.png` |
| Benchmark pitfall | §9 (three pitfalls); `figures/final/pitfalls.png` |
| System configuration incl. NUMA, pinning | §1 |

## Project 3 — SSD Performance Profiling

| Required item | Where |
|---|---|
| Data-loss safety | §1; `scripts/common.sh` (`guard_target`), file target only, byte-bounded writes |
| QD=1 latency for 4 KiB random and 128 KiB sequential R/W, with p95/p99 | §3; `figures/qd1_latency_table.md`, `qd1_latency.png` |
| Block-size sweep (throughput and latency from the same runs) | §4; `figures/bs_sweep_qd1.png`, `bs_sweep_qd32.png` |
| Read/write mix sweep | §5; `figures/rwmix.png` |
| QD / parallelism sweep, knee, Little's Law | §6; `figures/qd_sweep_*.png`, `littles_law_table.md` |
| Tail latency at mid-QD and near the knee | §7; `figures/tail_latency.png`, `tail_latency_table.md` |
| Working set / LBA range; device state (burst vs steady state) | §8; `figures/workingset.png`, `sustained_write.png` |
| Misleading setup | §9; `figures/misleading_setup.png`, `figures/kyber/`, `data/kyber/` |
| FIO configs | `configs/base.fio` and the per-run `.params` files |
