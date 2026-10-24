# Project 2: Cache & Memory Performance Profiling

Home-built tools (Intel MLC does not run on AMD) for a Ryzen 9 9950X (Zen 5; L1d 48 KiB/core,
L2 1 MiB/core, L3 32 MiB per CCD; CCD0 = cpus 0-7,16-23, CCD1 = 8-15,24-31).

## Build / run / plot
```
make                                   # -> bin/{latency,bandwidth,mlp,kernel_miss,tlb}   (gcc, -O3 -march=native, warning-free)
QUICK=1 scripts/run_all.sh             # tiny sanity config -> data/raw/sanity/<experiment>/   (seconds to a minute each)
scripts/run_all.sh                     # full config -> data/raw/final/  (long; do this under controlled settings)
cd ..   # back to the repo root
common/pyrun.sh p2-memory/scripts/process.py p2-memory/data/raw/sanity p2-memory/data/processed/sanity
for p in latency bandwidth intensity kernel pitfall; do
  common/pyrun.sh p2-memory/scripts/plot_$p.py --in p2-memory/data/processed/sanity --out p2-memory/figures/sanity; done
```
`plot_kernel.py` draws both the cache-miss (exp 6) and TLB (exp 7) figures. Every run script calls
`../common/env_capture.sh` and writes `env.txt` next to the raw CSVs. Raw CSVs keep every repetition;
`process.py` writes median / q1 / q3 / std / min / max / n per point to `data/processed/`.
Run-script knobs (env vars): `QUICK`, `OUT`, `CPU` (single-thread cpu, default 4), `THREAD_CPUS`
(default `4,5,6,7,8,9,10,11` = 4 cores on each CCD; QUICK uses `4,5,6,7`), `REPS_LAT` (11), `REPS_BW` (5), `SECS` (0.5).
Perf counters need `perf_event_paranoid<=2` (user-space only counting works); events used are listed below.

## Tools (src/)
| Tool | What it measures |
|---|---|
| `latency` (original, extended) | single-thread dependent-load chase: ns/access vs size, pattern, stride, page size. New: `--cycles` (real core GHz from user-space cycles counter), `--header`, `--cpu`, `--ctl/--ack`, THP verification column `thp_frac`. 2 MiB-aligned buffers now (so THP can cover them). |
| `bandwidth` | multi-thread pinned read / write / mixed bandwidth, seq/random, stride, access size |
| `mlp` | K interleaved dependent chains per thread (memory-level parallelism) and MLC-style loaded latency (probe + background streamers with injected delay) |
| `kernel_miss` | `z=x*y` / SAXPY with footprint, stride, random block order, page mode, perf-gated |
| `tlb` | one node per 4 KiB page chase, random or sequential page order, 4k vs THP, perf-gated |
| `common.h` | pinning, 2 MiB-aligned mmap + madvise, `/proc/self/smaps` THP check, perf `--control` hooks, cycle counter |

## Experiments -> scripts -> figures
| # | Requirement | Script | Raw files | Plot |
|---|---|---|---|---|
| 1 | zero-queue latency table (ns + cycles) | `run_latency.sh`, `measure_freq.sh` | `latency/latency.csv` | `processed/latency/zero_queue_table.csv` (ns, measured GHz, cycles = ns x GHz) |
| 5 | working-set sweep | `run_latency.sh` | same | `latency_working_set` |
| 2 | pattern & granularity | `run_pattern.sh` | `pattern/{latency,bandwidth}.csv` | `latency_pattern_stride`, `bandwidth_pattern_stride` |
| 3 | R/W mix | `run_rwmix.sh` | `rwmix/{bandwidth,loaded_latency}.csv` | `bandwidth_rwmix`, `loaded_latency_rwmix` |
| 4 | intensity / Little's law / knee | `run_intensity.sh` | `intensity/{mlp,loaded_latency}.csv` | `intensity_mlp`, `intensity_loaded_latency` |
| 6 | cache-miss impact | `run_kernel.sh` | `kernel/kernel.csv`, `kernel_perf.csv` | `kernel_cache_miss` |
| 7 | TLB-miss impact | `run_tlb.sh` | `tlb/tlb.csv`, `tlb_perf.csv` | `tlb_miss_impact` |
| 8 | pitfalls | `run_pitfall.sh` | `pitfall/p*.csv` | `pitfalls` |

## How things are implemented
**Latency**: Sattolo random single cycle (one node per `stride` bytes) or sequential; each hop depends on the previous load.
Core cycles come from a user-space `cycles` counter around the timed loop, so cycles = ns x measured GHz (do not assume nominal clock).
`measure_freq.sh` cross-checks with `perf stat` (cycles / task-clock).

**Bandwidth** (`bandwidth`): each thread owns a private buffer (first-touched after pinning), `size/stride` blocks, one *access* per block:
`--access 64` = one AVX-512 64 B load/store, `--access 8` = one scalar 8 B op (1/8 of the line is useful). Threads rendezvous at a barrier,
run until a common deadline; aggregate = total bytes / slowest thread time (per-thread min/max also reported).
Random order = in-register LCG block index (4 independent streams, sampling with replacement), so there is no index array whose traffic would pollute results;
the LCG costs a few cycles per access, so in-cache random bandwidth is partly instruction-bound.
**R/W mix**: `--rw R:W` repeats "R reads then W writes" in access order (7:3 = 70% reads, 1:1 = 50/50, 1:0, 0:1); op chosen by position in the sequence, not by address,
so reads and writes hit different lines within a pass. `--nt` makes writes non-temporal (streaming) stores.
**Traffic accounting**: `useful_GBps` = accesses x access bytes / time ("program bytes"); `line_GBps` = lines touched x 64 B / time;
`est_mem_GBps` = reads x 64 + writes x (128 normal stores: write-allocate read-for-ownership + write-back; 64 with NT). The last is only meaningful when footprint >> L3.
GB = 1e9 B, GiB = 2^30 B (both columns present). 100%-write with normal stores therefore moves ~2x the bytes the program wrote.

**Little's law** (`plot_intensity.py`): for the chase sweep, throughput is compared with the no-queueing prediction N x 64 B / R0 from the configured concurrency N and the independently measured idle latency R0; for the loaded-latency sweep, lines in flight are *inferred* as bandwidth x probe latency / 64 B (not fixed by construction).
**Intensity** (`mlp`): (a) K chains/thread, T threads -> outstanding = T x K; throughput = hops x 64 B / time; latency per hop = time/steps. Little's law
(outstanding = throughput x latency) is reported in `outstanding_littles`; for chase-only runs it equals T x K by construction, so the informative content is *where throughput stops growing
and latency starts to climb* (the knee, found with a Kneedle-style max-distance-from-chord rule in `plot_intensity.py`; judge it by eye too).
(b) MLC-style: one K=1 chase probe on THREAD_CPUS[0] + N background streaming threads, `--bgdelay D` adds D ~1-cycle adds after every 64 B line, `--bgrw` sets their mix.

**Kernel / TLB perf runs**: `perf stat -D -1 --control fifo:` with the program sending `enable`/`disable`, so counters cover only timed repetitions.
Events (all verified with `perf stat`): set A `cycles, L1-dcache-load-misses, l2_cache_req_stat.ic_dc_miss_in_l2 (L2 demand misses), l2_pf_miss_l2_hit_l3.l1_dc_l2_hwpf + l2_pf_miss_l2_l3.l1_dc_l2_hwpf (L2 HW-prefetch requests that miss L2 and hit L3 / also miss L3), ls_any_fills_from_sys.dram_io_all (L1d fills whose data came from DRAM, demand+prefetch)`;
set B `cycles, instructions, ls_l1_d_tlb_miss.all, ls_l1_d_tlb_miss.all_l2_miss (page walks), ls_any_fills_from_sys.local_ccx (L1d fills from L3/CCX)`; TLB runs use B's dTLB events plus DRAM fills. <=6 events per run = Zen 5's 6 core PMCs -> no multiplexing (`run_pct` column = 100).
Cross-check (1 GiB sequential read, 1 thread): `ls_any_fills_from_sys.dram_io_all` = 97% of the lines read, so it is the counter to use for DRAM traffic; for 100% normal stores `ls_any_fills_from_sys.all` = lines written (one RFO fill per stored line, confirming write-allocate) and ~0 with `--nt`.
`l2_cache_req_stat.*` only counts demand requests, so streaming kernels whose misses are hidden by hardware prefetch show few L2 "misses" yet many L3/DRAM fills; use `ls_any_fills_*` for traffic.

**TLB**: nodes sit one per page at a hashed line offset (avoids L1/L2 set aliasing). Cache footprint is only #pages x 64 B while the TLB footprint is #pages entries.
`thp_frac` (AnonHugePages/Size from `/proc/self/smaps` after faulting) is printed in every CSV: ~1 for THP runs, 0 for 4k runs. No hugetlbfs pages are reserved, so "huge" = THP via `MADV_HUGEPAGE`.
Spans above ~2 GiB also exceed the 64 MiB of L3 for the node lines themselves; compare 4k vs THP at equal span.

**Pitfalls** (`run_pitfall.sh`): P1 "DRAM" test of 16 MiB that fits in L3 (vs 1 GiB; and 4x16 MiB across one CCD); P2 `--nowarm`: reading never-written memory maps the (huge) zero page, so a 256 MiB "DRAM" read runs at cache speed;
P3 careless pinning: 2 threads on SMT siblings of one core (cpus N, N+16) vs 2 physical cores, at L1- and L2-sized buffers (shared L1/L2 and load ports halve bandwidth; 2 x 768 KiB overflows the shared L2). Frequency pitfall: `core_ghz` columns record the real clock; the governor is not changed by these scripts (needs sudo; see `../common/bench_mode.sh`).

## Limitations
- Single NUMA node: no remote-memory experiments. Shared machine: other jobs perturb DRAM numbers; use the controlled mode for final data.
- Random order is sampling with replacement (bandwidth tool) -- lines may repeat within a pass; irrelevant for large buffers.
- Supported R:W ratios are 1:0, 0:1, 7:3, 1:1 (compile-time unrolled); others need a new `PICK` line in `bandwidth.c`.
- MLP chains use disjoint sub-buffers of `size/K` each; K beyond the L1 miss-buffer capacity (~tens) only adds queueing.
- Hardware prefetchers cannot be disabled without root, so sequential results include prefetch benefit.
- THP availability depends on free contiguous memory; always check `thp_frac`.
