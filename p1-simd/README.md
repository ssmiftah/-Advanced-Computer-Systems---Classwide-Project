# Project 1: SIMD advantage profiling (Ryzen 9 9950X / Zen 5)

Four kernels (SAXPY, dot product, elementwise multiply, 3-point stencil) in float32 / float64 / int32,
compiled with several flag sets into separate binaries and measured with one timing harness.

## Quick start (run from `p1-simd/`; Python through `common/pyrun.sh` from the repo root: a venv, or uv if installed)

```
make                                   # bin/simd_<build>, bin/membw, bin/peakflops, reports/*
scripts/run_all.sh                     # build + all experiments + process + plots (real data; run under bench mode)
QUICK=1 OUT_ROOT=$PWD/data/raw/sanity scripts/run_all.sh    # ~25 s smoke test -> data/raw/sanity, data/processed/sanity, figures/sanity
```
Individual steps: `scripts/run_{vecreport,bandwidth,speedup,locality,align_tail,stride_gather,dtype}.sh`, then (from the repo root)
```
common/pyrun.sh p1-simd/scripts/process.py --raw p1-simd/data/raw --out p1-simd/data/processed
for p in speedup locality align_tail stride_gather dtype roofline; do common/pyrun.sh p1-simd/scripts/plot_$p.py; done   # PNG+PDF into p1-simd/figures
common/pyrun.sh p1-simd/scripts/plot_roofline.py --bw-gibs <P2 DRAM GiB/s> --bw-label "DRAM, multi-thread (P2)"
```
Run-script knobs (env): `CPU` (pin core, default 3), `SAMPLES` (15), `MINMS` (min ms per sample, 8), `REPEATS` (independent process
invocations per configuration, seeds 12345.., default 3; QUICK 1), `BUILDS`, `QUICK=1`, `OUT_ROOT`. Full `run_all.sh` takes ~45 min
with the defaults (~15 min per repeat; align_tail is ~half of it).
Every run script pins with `taskset -c $CPU` and writes `../common/env_capture.sh` output + build flags to `<outdir>/env.txt`
next to the raw CSV. Run `sudo ../common/bench_mode.sh on` first for the real collection (scripts do not change system state).

## Layout
| path | purpose |
|---|---|
| `src/kernels_impl.inc`, `kernels.c`, `kernels.h` | the kernels (separate TU, `noinline,noipa`, `restrict`); built once per flag set |
| `src/ref.c` | scalar reference (`-O2 -fno-tree-vectorize -fno-tree-slp-vectorize -ffp-contract=off`), the correctness oracle |
| `src/main.c`, `harness_t.inc`, `perfcyc.h` | timing + correctness harness (one CLI, CSV of raw samples), perf cycle counter |
| `src/membw.c`, `src/peakflops.c` | single-thread read/triad bandwidth vs size; empirical FMA peak (roofline inputs) |
| `Makefile` | builds + vectorization reports (`make vec-reports`, `make clang-reports`) |
| `scripts/run_*.sh`, `common.sh` | one script per experiment |
| `scripts/process.py` | raw -> `data/processed/*_summary.csv` (median/IQR) and `*_speedup.csv` |
| `scripts/plot_*.py`, `plot_common.py` | figures (log-x, cache-boundary lines, IQR bands) |
| `scripts/vec_check.py` | extracts per-kernel vectorization facts from objdump + compiler reports |
| `reports/` | `<build>.vec-optimized.txt` / `.vec-missed.txt` (GCC -fopt-info-vec), `<build>.objdump.txt`, `flags.txt` (compiler versions + flags), `vec_summary.{csv,md}`, `vec_snippets.md` |
| `REPORT_NOTES.md` | what the sanity runs showed / surprises (not the final analysis) |

## Builds (GCC 16.2.1; Clang 23.1.3 available for report comparison via `make clang-reports`)
All: `-O3 -std=gnu17 -Wall -Wextra` + the flags below, applied to `kernels.c` only (harness and reference are identical in all binaries).
| binary `bin/simd_<b>` | extra flags | meaning |
|---|---|---|
| `scalar` | `-fno-tree-vectorize -fno-tree-slp-vectorize` | no SIMD loops (report is empty; objdump shows only `*ss/*sd` scalar ops). Baseline x86-64 ISA (SSE2 scalar math, no FMA) |
| `scalar_znver5` | `-march=znver5 -fno-tree-vectorize -fno-tree-slp-vectorize` | control: same ISA/tuning as `znver5` (scalar `vfmadd*ss`, VEX) but no vectorization; separates SIMD width from FMA/ISA effects (exp. 1 only) |
| `sse` | (none) | GCC default auto-vectorization, baseline ISA = SSE2 (128-bit) |
| `avx2` | `-mavx2 -mfma` | 256-bit + FMA |
| `znver5` | `-march=znver5` | CPU-targeted; GCC 16 already picks 512-bit zmm here |
| `znver5_pv512` | `-march=znver5 -mprefer-vector-width=512` | built to test whether the flag is needed: generated code is identical to `znver5` (see `reports/vec_summary.md`) |
| `*_fm` (sse/avx2/znver5/pv512) | above + `-fassociative-math -fno-signed-zeros -fno-trapping-math` | allows FP reduction reassociation (narrower than -ffast-math) so the dot product can really use vector accumulators |
Note: `scalar`->`avx2/znver5` speedups combine vector width *and* FMA contraction (`a*x+y` -> one FMA); `sse` has neither.
`scalar_znver5` measures the FMA/ISA part alone: in review runs (16 KiB, f32) saxpy 1.045 vs 1.045 cyc/elem, stencil 1.51 vs 1.68,
i.e. the speedups are essentially SIMD width.

## Harness / methodology
* Timing: `clock_gettime(CLOCK_MONOTONIC_RAW)`. Per configuration: correctness check, then calibration (kernel looped K times
  until one sample >= `MINMS` ms, which doubles as warm-up), one extra warm run, then `SAMPLES` timed samples of K calls each.
  **All samples are written** (one CSV row each, with the `seed` of the invocation); `process.py` pools the `REPEATS` invocations
  of a configuration (K may differ between them, so K is not a grouping key) and gives median and IQR over all samples.
  Why repeats: at DRAM sizes the time differs by 5-15% *between processes* (e.g. scalar saxpy f32 128 MiB: 4.8-6.2 ms across
  invocations, <1% within one; vector builds were stable), presumably physical page placement / DRAM bank mapping;
  within-process IQR alone underestimates the uncertainty.  Per-call time = sample / K. For DRAM-sized sets K is small (1-7).
* Cycles: measured with `perf_event_open(PERF_COUNT_HW_CPU_CYCLES)` in user space, read around each sample on the pinned thread. It
  counts real core-clock cycles, so cycles/element is correct even when boost frequency varies (we do **not** assume TSC == core clock).
  `ghz = cycles / ns` is stored per sample as the effective frequency (~5.4-5.6 GHz in sanity runs). If the counter is unavailable
  the columns are -1/NaN and a warning is printed.
* Anti-optimization: kernels in a separate TU, `noinline,noipa`, runtime `n`, results (dot sums) accumulated and stored to a
  volatile sink. Data: random sign, magnitude in [0.5,1): no zeros/denormals; SAXPY uses a=1e-5 so repeated in-place updates grow only linearly.
  Integer type `i32` is `uint32_t` (wrap-around is defined; "GFLOP/s" for i32 means Gop/s).
* Correctness (fail loudly, exit status 3, message on stderr) before timing, for every kernel/type/variant/size/offset:
  elementwise kernels vs the scalar reference with tolerance `4*eps*(|ref|+sum|terms|)` (the only legitimate difference is FMA contraction);
  multiply exact; integers exact; dot vs a long-double sum of exact products with tolerance
  `4*eps*sqrt(n)*sqrt(sum p_i^2)` (zero-mean data => rounding errors random-walk; the rigorous `n*eps*sum|p|` bound is vacuous at large n);
  both the reference and the kernel must satisfy it.
* Allocation: `aligned_alloc(64)`; arrays get distinct 64B-multiple pads (x +0, y +17 lines, z +34 lines) to avoid 4 KiB-aliasing; the
  requested byte offset (`--offx/--offy/--offz/--offset`) is added on top; the realized `addr & 63` is recorded (`mis_x`, `mis_y`).
* Working set: `--ws-kib` = nominal footprint of all arrays (`narr * n * sizeof(T)`, narr = 3 for multiply else 2), n rounded down to a
  multiple of 64 (no tail for any ISA). `--n` gives an explicit element count (used for tail / stride studies). Cache boundaries drawn
  on plots: L1d 48 KiB, L2 1 MiB (per core), L3 32 MiB (per CCD).
* Stride: `x[i*s]` (s = 1,2,4,8), n fixed so FLOPs are fixed, x allocated n*s elements. Gather: `x[idx[i]]` with `perm` = uniformly random
  permutation, `block` = random permutation of 16-element (64 B for f32) blocks, contiguous inside a block. Stride/gather kernels exist for SAXPY and dot.

## Per-element cost model (nominal; used for GFLOP/s, GiB/s and roofline arithmetic intensity)
| kernel | FLOP/elem | bytes/elem (algorithmic) | HW traffic incl. write-allocate | AI f32 (FLOP/B) |
|---|---|---|---|---|
| SAXPY `y=a*x+y` | 2 | 3*s (read x, read y, write y) | 3*s (y line already read) | 2/12 = 0.167 |
| dot | 2 | 2*s | 2*s | 2/8 = 0.25 |
| multiply `z=x*y` | 1 | 3*s | 4*s (z write-allocates) | 1/12 = 0.083 |
| stencil | 5 (3 mul + 2 add; n-2 outputs) | 2*s (x read once, neighbours reused; write y) | 3*s | 5/8 = 0.625 |
(s = sizeof element; gather adds 4 B/element for the index array. Strided loads physically fetch whole 64 B lines, so reported GiB/s is *useful* bandwidth.)

## Experiments -> scripts -> figures
| # | experiment | script | raw dir | figures |
|---|---|---|---|---|
| 1 | scalar vs auto-vec, all kernels, size sweep (speedup, GFLOP/s, GiB/s, cyc/elem) | `run_speedup.sh` | `data/raw/speedup` | `speedup_vs_size`, `speedup_gflops`, `speedup_cycles` |
| 2 | locality sweep 8 KiB-1 GiB (dense points near 48 KiB/1 MiB/32 MiB) | `run_locality.sh` | `locality` | `locality_gibs/cycles/gflops` |
| 3 | alignment offsets (0,4,8,16,32,48 B; x,y,z together or x only; L1/L2/DRAM) and tails (n mod 16/8 != 0, small n), f32+f64 | `run_align_tail.sh` | `align_tail` | `align_f32/f64`, `tail_f32/f64` |
| 4 | unit vs stride 2/4/8 vs gather perm/block, L1..DRAM | `run_stride_gather.sh` | `stride_gather` | `stride_cycles`, `stride_gibs` |
| 5 | f32 vs f64 vs i32 at equal byte footprint | `run_dtype.sh` | `dtype` | `dtype_gflops`, `dtype_speedup` |
| 6 | vectorization verification (opt-info, objdump, snippets) | `run_vecreport.sh` -> `make vec-reports` | `reports/` | `reports/vec_summary.md`, `vec_snippets.md` |
| 7 | roofline (measured peak + measured single-thread bandwidth, or external bandwidth) | `run_bandwidth.sh`, `plot_roofline.py` | `bandwidth` | `roofline` |
| 8 | negative examples: (a) FP dot without `-fassociative-math` (serial reduction; compare `*` vs `*_fm` in exp. 1/5 and `reports/vec_summary.md`; ~1.0x, and 0.9x for znver5 at DRAM), (b) SAXPY/mul vectorized but only ~1.1-1.7x at DRAM sizes (exp. 1/2; scalar side varies between runs) | (from 1,2,6) | | |

## Peak FLOP estimate and bandwidth (roofline)
* Theoretical fp32 peak per core = 2 FMA pipes x 16 lanes (512-bit) x 2 FLOP = **64 FLOP/cycle** (fp64: 32), times the *measured* core clock
  (`peakflops` reports cycles and ns, so GHz is measured, not assumed). The 2x512-bit FMA datapath on the desktop Zen 5 part is from public
  microarchitecture descriptions (uncertain to the extent that I did not re-verify against AMD documentation); `bin/peakflops`
  verifies it empirically with 16 independent FMA chains: sanity run gave 63.98 FLOP/cycle zmm, 31.99 ymm, 16.0 xmm, 31.99 fp64-zmm.
  The plot uses the measured zmm number as the compute roof (dashed: ymm/xmm roofs, dotted: theoretical).
* Bandwidth: `bin/membw` = **single-thread** 512-bit streaming read (8 accumulators) and triad vs buffer size, giving per-level ceilings
  (L1/L2/L3/DRAM). A single core cannot saturate DRAM; the multi-thread DRAM bandwidth from Project 2 is the machine ceiling.
  Pass it with `plot_roofline.py --bw-gibs X --bw-label ...`; the single-thread kernels in this project should be compared with the single-thread ceiling.

## Known limitations
* Single thread, one pinned core (SMT sibling not controlled by the scripts; use bench mode / an idle sibling for the real run).
* GCC only for the timed builds; clang is used for optional vectorization remarks (`make clang-reports`). `-fassociative-math` builds
  change dot/stride-dot results by reassociation (checked against the tolerance above).
* GCC did not emit `vgather*` on znver5 (cost model), so the "gather" kernels are scalar loads + vector math, which is the honest compiler
  outcome but not a study of the hardware gather instruction. Intrinsics would be needed for that. (Checked: `-mtune-ctrl=use_gather_2parts,
  use_gather_4parts,use_gather_8parts` makes GCC emit `vgatherqpd` for the f64 gather kernels only; f32 with `uint32_t` indices still
  gets none (presumably because `vgatherdps` takes *signed* 32-bit indices; untested with `int32_t` indices).)
* Misalignment is created in elements' natural alignment (4/8 B granularity); offsets that are not multiples of the element size are not tested.
* `n_mod_vw` is relative to a 512-bit register (16 f32 / 8 f64 lanes); with narrower builds fewer remainders exist.
* i32 uses 32-bit unsigned multiply; baseline SSE2 lacks `pmulld`, so the `sse` i32 numbers include the `pmuludq` emulation.
* Nominal bandwidth ignores write-allocate and strided over-fetch (see table above).
