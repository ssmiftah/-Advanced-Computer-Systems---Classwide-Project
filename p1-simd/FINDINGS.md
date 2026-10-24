# Project 1 — SIMD Advantage Profiling: Findings

All numbers come from the final run in `data/raw/final/` (processed tables in `data/processed/final/`,
figures in `figures/final/`). Each data point is the median of 45 timed samples: 15 samples from each of 3
separate process runs. Error bars and ranges are interquartile ranges (IQR).

## 1. Setup

| Item | Value |
|---|---|
| CPU | AMD Ryzen 9 9950X (Zen 5), 16C/32T, AVX-512 (F/VL/BW/DQ) with two 512-bit FMA pipes |
| Caches | L1d 48 KiB/core, L2 1 MiB/core, L3 32 MiB per CCD (2 CCDs) |
| Memory | 4 × 16 GiB DDR5-4800 DIMMs running at 3600 MT/s, dual channel (57.6 GB/s theoretical) |
| OS / kernel | CachyOS, Linux 7.3.0-5-cachyos |
| Compiler | GCC 16.2.1 (timed builds). Clang 23.1.3 was used only for optional vectorization remarks |
| Frequency | `performance` governor, boost **on**. The core clock was measured on every sample with `perf_event_open` cycles; it ran at 5.5–5.7 GHz |
| SMT | on. The benchmark was pinned to CPU 3 with `taskset`; its SMT sibling (CPU 19) was idle but not isolated |
| Timing | `CLOCK_MONOTONIC_RAW`; each timed sample loops the kernel K times so it lasts ≥ 8 ms; 15 samples × 3 runs |
| Data | Arrays initialised to non-trivial values (no zeros, no denormals); outputs consumed so the compiler cannot delete the work |
| Correctness | Every run is checked against a scalar reference (`src/ref.c`, built with `-O2 -fno-tree-vectorize -ffp-contract=off`). Any mismatch aborts the run (exit 3). The reviewer also ran a separate sweep: 480 configurations, 0 failures |

Build variants (exact flags are in `reports/flags.txt`):

| Build | Flags (on top of `-O3`) | Purpose |
|---|---|---|
| `scalar` | `-fno-tree-vectorize -fno-tree-slp-vectorize` | Scalar baseline |
| `scalar_znver5` | same plus `-march=znver5` | Control: scalar code that can use FMA. Separates the vector-width gain from the new-ISA gain |
| `sse` | none (default x86-64, SSE2) | Default auto-vectorization, 128-bit |
| `avx2` | `-mavx2 -mfma` | 256-bit |
| `znver5` | `-march=znver5` | Widest available, 512-bit (zmm) |
| `*_fm` | `-fassociative-math -fno-signed-zeros -fno-trapping-math` | Allows floating-point reductions to be reordered |

`-mprefer-vector-width=512` produced identical machine code to plain `-march=znver5` with GCC 16.2, so it is
not reported separately.

## 2. Hypotheses (stated before the runs)

1. When the data fits in L1, the speedup should approach the lane count: about 4× for SSE, 8× for AVX2 and
   16× for AVX-512 with float32. In practice it would be lower because of loads/stores per FLOP and
   loop overhead.
2. Once the working set exceeds the L3, every kernel becomes memory-bound. All builds should then converge
   to about 1×, because one core already streams DRAM at about 55 GB/s whatever the instruction width.
3. The floating-point dot product will **not** vectorize without permission to reorder additions, because
   IEEE addition is not associative. Integer dot products will vectorize.
4. Misaligned 512-bit accesses split cache lines and should cost measurably in L1. That cost should
   disappear once memory bandwidth is the bottleneck.
5. Non-unit stride and gather patterns waste most of each cache line, so they should erase most of the SIMD
   gain.

## 3. Vectorization verification

Evidence comes from `reports/vec_summary.md`, which classifies each kernel's hot loop from objdump, and
`reports/vec_snippets.md`, which holds short disassembly excerpts. The raw GCC `-fopt-info-vec` reports
are kept alongside them.

| float32, hot loop | saxpy | dot | mul | stencil | gather saxpy |
|---|---|---|---|---|---|
| scalar | S | S | S | S | S |
| sse | V/xmm | **P/xmm** | V/xmm | V/xmm | V/xmm |
| avx2 | V/ymm+fma | **P/ymm** | V/ymm | V/ymm+fma | V/xmm+fma |
| znver5 | V/zmm+fma | **P/zmm** | V/zmm | V/zmm+fma | V/xmm+fma |
| znver5_fm | V/zmm+fma | V/zmm+fma | V/zmm | V/zmm+fma | V/xmm+fma |

V = vector, S = scalar, P = **partial**: the multiplies are packed (`vmulps`), but the sum is a serial
chain of scalar `vaddss`. GCC still prints "loop vectorized" for the P loops, which is why the disassembly
is treated as the source of truth here, not the compiler report. The znver5 loops use unaligned
`vmovups` with a **masked epilogue** (k-register stores) and no alignment peeling. GCC emitted no
`vgather*` instruction for float32, so the "gather" kernels do scalar indexed loads feeding vector
arithmetic.

## 4. Scalar vs SIMD across working-set sizes

Figures: `figures/final/speedup_vs_size.png`, `speedup_gflops.png`, `speedup_cycles.png`.

Speedup over `scalar`, float32, unit stride. Each column is the size nearest to that cache level.
IQR bounds are in `data/processed/final/speedup_speedup.csv`; most are within ±2%.

| Kernel | Build | L1 (16 KiB) | L2 (512 KiB) | L3 (16 MiB) | DRAM (1 GiB) |
|---|---|---|---|---|---|
| saxpy | sse | 3.70 | 3.58 | 3.30 | 1.02 |
| saxpy | avx2 | 6.86 | 6.33 | 3.32 | 1.02 |
| saxpy | znver5 | **10.14** | 6.49 | 4.04 | **1.02** |
| mul | znver5 | 10.04 | 4.73 | 2.83 | 1.06 |
| stencil | znver5 | 10.16 | 7.32 | 5.02 | 1.16 |
| dot | znver5 (strict FP) | **0.98** | 0.98 | 0.97 | 0.98 |
| dot | znver5_fm | **27.6** | 14.9 | 6.34 | 2.26 |
| saxpy | scalar_znver5 (control) | 1.00 | 1.00 | 1.01 | 0.98 |
| stencil | scalar_znver5 (control) | 1.11 | 1.12 | 1.12 | 1.08 |

Cost per element in core cycles. The L1 throughput for znver5 saxpy is 110 GFLOP/s:

| Kernel | scalar (L1) | znver5 (L1) | scalar (DRAM) | znver5 (DRAM) |
|---|---|---|---|---|
| saxpy | 1.019 | 0.100 | 1.527 | 1.518 |
| stencil | 1.676 | 0.162 | 1.718 | 1.514 |
| dot (strict) | 1.947 | 2.002 | 2.007 | 2.064 |

Interpretation:

- **In L1, speedup reaches about 10× with 512-bit vectors, not 16×.** The znver5 saxpy loop runs at
  0.10 cycles/element, i.e. 1.6 cycles per 16-element vector. Each vector needs two loads, one FMA and
  one store. Zen 5's load/store unit handles about two 512-bit loads and one 512-bit store per cycle
  (published figure, not measured here), so the best case is about 1 cycle per vector. We measure 1.6.
  The FMA units are far from busy: 2 FLOP/elem × 10 elem/cycle = 20 FLOP/cycle out of the 64 measured
  peak. The limit is load/store throughput plus loop overhead, not arithmetic.
- **The scalar saxpy speed limit is exactly 1 element per cycle** (1.019 cycles/element) at every size up
  to L3. That is why scalar code looks size-insensitive until DRAM: the CPU is busy with instructions,
  not waiting for memory.
- **The control build proves the gain comes from vector width.** Scalar code compiled for Zen 5 can use
  FMA, yet it gains nothing for saxpy (1.00×) and only 11% for the stencil, which has three multiply-adds
  per element. Almost all of the speedup comes from wider vectors.
- **Speedup scales with lane count.** SSE (4 lanes) gives 3.7×, AVX2 (8 lanes) 6.9×, and AVX-512
  (16 lanes) 10.1×.

## 5. Locality sweep: where the SIMD gain disappears

Figures: `figures/final/locality_gflops.png`, `locality_gibs.png`, `locality_cycles.png`, with
vertical lines at 48 KiB, 1 MiB and 32 MiB.

The gain falls in steps at each cache boundary, while scalar code stays flat until DRAM:

- **L1 → L2 (around 48 KiB):** znver5 saxpy drops from about 110 to 65 GFLOP/s, because L2 cannot feed
  two 64-byte loads per cycle. AVX2 drops much less (80 → 67 GFLOP/s) because it asks for half the
  bandwidth. **In L2, AVX2 and AVX-512 run at almost the same speed**: the cache, not the instruction
  width, is the limit.
- **L2 → L3 (around 1 MiB):** all vector builds converge at about 35 GFLOP/s for saxpy.
- **L3 → DRAM (32–64 MiB):** a steep fall. The L3 is 32 MiB per CCD and a single thread uses only one
  CCD's L3, so the edge appears at 32 MiB, not at the 64 MiB total. By 128 MiB every build, including
  scalar, sits at about 7.5 GFLOP/s (saxpy), about 45 GB/s of algorithmic traffic.
- **The stencil keeps a gain longest** (5× at 16 MiB, 1.16× at 1 GiB). The scalar stencil is
  compute-bound at about 1.7 cycles/element, with three multiplies per element on two FP pipes. Even
  at DRAM sizes the scalar version is not purely waiting on memory.

## 6. Alignment and tail handling

Figures: `figures/final/align_f32.png`, `align_f64.png`, `tail_f32.png`, `tail_f64.png`.

**Alignment.** saxpy f32, n = 2048 elements (16 KiB, L1-resident), cycles per element, with x and y both
shifted by the given byte offset from a 64-byte boundary:

| Build | 0 B | 4 B | 8 B | 16 B | 32 B | 48 B |
|---|---|---|---|---|---|---|
| scalar | 1.019 | 1.019 | 1.019 | 1.019 | 1.019 | 1.019 |
| sse (16 B vectors) | 0.276 | **0.323** | **0.323** | 0.276 | 0.276 | 0.276 |
| avx2 (32 B vectors) | 0.149 | **0.195** | **0.195** | **0.195** | 0.149 | **0.195** |
| znver5 (64 B vectors) | 0.100 | **0.133** | **0.133** | **0.133** | **0.133** | **0.133** |

The pattern matches cache-line splits exactly:

- **A vector of width W bytes splits a 64-byte line whenever the offset is not a multiple of W.** SSE is
  slow only at 4 and 8 B. AVX2 is fine at 32 B, because 32-byte loads at offset 32 never cross a line.
  AVX-512 is penalised at every non-zero offset, since every 64-byte access then spans two lines.
- **The penalty is about +33% in L1 and +42% in L2** (n = 65536: 0.132 → 0.188 cycles/element).
- **At 384 MiB (DRAM) there is no consistent alignment effect.** All offsets fall within ±5% of each
  other, which is within run-to-run noise.

**Tail (remainder) handling.** znver5 saxpy, time per call:

| n | 16 | 17 | 32 | 33 | 64 | 65 | 1024 | 1025 |
|---|---|---|---|---|---|---|---|---|
| ns/call | 2.7 | 3.9 | 2.7 | 3.8 | 2.7 | 3.8 | 18.4 | 18.9 |

A single leftover element costs about 1.1 ns (about 6 cycles) for the masked epilogue, whatever n is.
At n = 64 that is +40%; at n ≥ 1024 it is under 3%. For tiny arrays the per-call overhead dominates:
at n = 16 the AVX-512 build (2.7 ns) is only 1.5× faster than scalar (4.0 ns) and slower than SSE/AVX2
(2.2–2.3 ns), because the AVX-512 epilogue/masking setup costs more than the work. The AVX2 build barely
notices remainders (2.9 vs 3.0 ns at 64/65).

## 7. Stride and gather

Figures: `figures/final/stride_cycles.png`, `stride_gibs.png`.

saxpy f32, znver5. The FLOP count is fixed, only the access pattern changes. "Useful GiB/s" counts only
the bytes the kernel actually uses.

| Pattern | L1 (16 KiB) cycles/elem | DRAM (128 MiB) cycles/elem | DRAM useful GiB/s | Speedup vs scalar, L1 |
|---|---|---|---|---|
| unit stride | 0.100 | 1.236 | 51.4 | 10.2× |
| stride 2 | 0.596 | 1.888 | 33.5 | 1.75× |
| stride 4 | 0.583 | 2.860 | 22.2 | 1.79× |
| stride 8 | 0.804 | 4.624 | 13.7 | 1.33× |
| gather (block-random) | 1.015 | 9.711 | 8.8 | 1.16× |
| gather (full permutation) | 1.015 | 10.81 | 7.9 | 1.18× |

- **In L1, any non-unit stride removes most of the SIMD gain** (10× → 1.3–1.8×). With no contiguous
  vector load, the compiler must assemble each vector from scalar loads or shuffles, and the load ports
  become the bottleneck.
- **In DRAM, cost tracks cache lines touched.** At stride 8 (32 B apart for f32) each element uses
  4 of the 64 bytes in its line, so useful bandwidth falls about 4× (51 → 13.7 GiB/s). Gather is worst
  because random lines also defeat the hardware prefetcher.
- **Block-random gather is about 10% better than a full permutation**, because neighbouring indices
  usually land in the same page and cache line.

## 8. Data types

Figures: `figures/final/dtype_speedup.png`, `dtype_gflops.png`.

znver5 speedup over scalar:

| Kernel | f32 L1 | f64 L1 | i32 L1 | f32 DRAM (256 MiB) | f64 DRAM |
|---|---|---|---|---|---|
| saxpy | 10.1 | 5.0 | 11.3 | 1.20 | 1.39 |
| stencil | 9.8 | 4.9 | 11.8 | 1.92 | 1.33 |
| dot | 0.98 | 0.99 | **12.1** | 0.91 | 1.00 |

- **The f64 gain is half the f32 gain,** because a zmm register holds 8 doubles instead of 16 floats.
  Throughput halves to match: saxpy runs at 110 vs 54 GFLOP/s in L1.
- **At DRAM sizes, f64 is about half as fast in GFLOP/s** (3.8 vs 7.6): each element is twice the
  bytes, so arithmetic intensity halves.
- **Integer dot vectorizes without any special flags (12× in L1),** because integer addition is
  associative. Floating-point dot does not. This isolates the cause of the negative example in §10 as
  the IEEE reordering rule, not the loop shape.

## 9. Roofline

Figure: `figures/final/roofline.png`.

All ceilings come from measurements on this machine, single thread:

| Ceiling | Value | Source |
|---|---|---|
| fp32 peak, zmm FMA | **355.6 GFLOP/s** (63.97 FLOP/cycle × 5.56 GHz) | `src/peakflops.c` |
| fp32 peak, ymm / xmm | 178.8 / 89.7 GFLOP/s | same |
| fp64 peak, zmm | 175.9 GFLOP/s | same |
| L1 read bandwidth | 640 GiB/s (687 GB/s) | `src/membw.c` |
| DRAM read bandwidth | 51.1 GiB/s (54.9 GB/s) at 1 GiB | same |
| Triad bandwidth (DRAM) | 30.3 GiB/s | same |

The measured 64 FLOP/cycle confirms two 512-bit FMA pipes (2 pipes × 16 lanes × 2 FLOP). The DRAM ridge
point is 355.6 / 54.9 ≈ **6.5 FLOP/byte**.

Arithmetic intensity (algorithmic bytes, f32):

| Kernel | FLOPs per element | Bytes per element | AI (FLOP/B) | DRAM roof (GFLOP/s) | Measured at DRAM (GFLOP/s) |
|---|---|---|---|---|---|
| saxpy | 2 | 12 (read x, y; write y) | 0.167 | 9.2 | 7.4 |
| dot | 2 | 8 | 0.25 | 13.7 | 12.9 (fm) / 5.5 (strict) |
| mul | 1 | 12 | 0.083 | 4.6 | 2.8 |
| stencil | 5 | 8 | 0.625 | 34.3 | 18.8 |

Every kernel's AI is 10–80× below the ridge point, so all four are **memory-bound at DRAM sizes**. That
is why the speedups converge to about 1× (Hypothesis 2 confirmed):

- **The fast-math dot reaches 94% of its DRAM roof.** It only reads, which matches how the roof was
  measured.
- **saxpy, mul and stencil sit 40–80% of their roofs.** They also write, and the roof was measured with
  reads only (the triad ceiling, 30 GiB/s, is a better bound for kernels that write). For mul and
  stencil the real traffic also includes write-allocate reads of z/y, which the algorithmic byte count
  omits. That raises their effective bytes per element to 16 and 12.
- **The strict dot is below the roof in every cache level.** It is limited by its add latency
  (2 cycles/element), not by memory or FLOPs.

## 10. Negative examples

**(a) A loop GCC calls "vectorized" that gives no speedup: the floating-point dot product.** GCC's report
says the loop was vectorized, yet the speedup is 0.97–1.01× at every size and every width; znver5 is
even 2–3% slower than scalar. The disassembly shows why: the multiplies are packed, but the 16 products
are then added one by one through a serial `vaddss` chain. The loop is limited by the 3–4 cycle FP-add
latency, about 2 cycles per element. With `-fassociative-math` the compiler uses 4 independent zmm
accumulators and reaches **27.6× in L1**. The remedy changes rounding, so results differ from the scalar
reference in the last bits. The correctness check uses a tolerance that grows with n for reductions only.

**(b) Correctly vectorized but no faster: saxpy at DRAM sizes.** The loop is fully vectorized with zmm
FMA, yet at 1 GiB it is 1.02× faster than scalar. Both run at about 1.52 cycles per element, which is
DRAM bandwidth (about 45 GB/s of algorithmic traffic). The mul kernel shows the same thing (1.06×).

## 11. Anomalies and open questions

- **Scalar dip around 256 MiB.** The scalar saxpy and stencil curves dip at 256 MiB, with wide IQR,
  then recover at 512 MiB–1 GiB (see `locality_gflops.png`). The vector builds do not dip. The reviewer
  measured large **between-process** variation in scalar runs at DRAM sizes (4.8–6.2 ms for the same
  configuration) and found that transparent huge page coverage was identical between runs. The likely
  cause is variation in physical page placement across DRAM banks/channels between processes, but this
  was not verified. The same variation explains why DRAM speedups for saxpy differ slightly between the
  speedup experiment (1.02× at 1 GiB) and the dtype experiment (1.20× at 256 MiB).
- **Single-thread read bandwidth is non-monotonic in the L2 range.** It reads 243 GiB/s at 64–256 KiB,
  315 GiB/s at 512 KiB and 204 GiB/s at 1 MiB (`bandwidth_read_summary.csv`). Possible causes are
  L1/L2 prefetcher behaviour or the loop-calibration step at those sizes; this was not investigated
  further.
- **AVX-512 slower than SSE/AVX2 for tiny arrays (n ≤ 33)** because of the masked prologue/epilogue
  setup cost. This is a real effect, but it only matters for very short loops.

## 12. Limitations

- **Single thread only,** as the assignment requires. The DRAM roof would be the same with more threads
  on this machine (see Project 2: one core already reaches about 95% of DRAM bandwidth).
- **Boost was left on** for realistic results. The core clock is therefore measured per sample rather
  than fixed, and cycles per element is computed from measured cycles.
- **The gather study measures software gather** (scalar loads), because GCC did not emit hardware
  `vgather` for f32.
- **The roofline uses algorithmic bytes;** write-allocate traffic is not counted.

## 13. AI-use note

- Claude Code (Anthropic) wrote all benchmark code, scripts and this findings draft, at the student's
  direction:
  - a Claude Sonnet agent wrote the initial code;
  - a separate Claude Opus agent reviewed it.
- **Fixes made:**
  - Error bars originally reflected only within-process noise. Between-process repeats were added.
  - A `scalar_znver5` control build was added, to separate the FMA/ISA gain from the vector-width gain.
  - Stale numbers in the notes were corrected.
- **Rejected after the review:** a suspected "AVX2 slower than scalar" stencil result at DRAM sizes. It
  was an artifact of too few samples and did not reproduce.
- **Checked independently of the code generator:** vectorization was confirmed from disassembly, not
  only from compiler messages, and all results were validated against the scalar reference.
- I am responsible for reviewing and understanding all claims above before submission.
