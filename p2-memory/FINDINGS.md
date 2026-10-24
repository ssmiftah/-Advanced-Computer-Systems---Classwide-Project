# Project 2 — Cache & Memory Performance Profiling: Findings

All numbers come from the final run in `data/raw/final/` (processed tables in `data/processed/final/`,
figures in `figures/final/`). Latency points are the median of 11 repetitions and bandwidth points the
median of 5. Error bars are interquartile ranges (IQR). Decimal GB/s (10⁹ B/s) is used throughout unless
GiB/s is stated.

## 1. Setup

| Item | Value |
|---|---|
| CPU | AMD Ryzen 9 9950X (Zen 5), 16C/32T, 2 CCDs (CPUs 0–7 and 16–23 on CCD0; 8–15 and 24–31 on CCD1) |
| Caches | L1d 48 KiB/core, L2 1 MiB/core, L3 32 MiB per CCD (not shared across CCDs) |
| DRAM | 4 × 16 GiB Micron CT16G48C40U5 DDR5 (rated 4800 MT/s), **running at 3600 MT/s**, 2 DIMMs per channel, dual channel. Theoretical peak = 2 ch × 8 B × 3.6 GT/s = **57.6 GB/s** |
| NUMA | 1 node |
| OS / kernel | CachyOS, Linux 7.3.0-5-cachyos; GCC 16.2.1; perf 7.2.11 |
| Frequency | `performance` governor, boost on. The core clock was measured during the latency runs: 5.70 GHz |
| SMT | On. Single-thread runs were pinned to CPU 4; multi-thread runs to CPUs 4–11 (4 cores on each CCD), so no SMT siblings were used unless the experiment called for it |
| Pages | Transparent huge pages (THP) were selected per buffer with `madvise(MADV_HUGEPAGE / MADV_NOHUGEPAGE)`. Actual coverage was read from `/proc/self/smaps` and recorded as `thp_frac`: 1.0 for every THP run and 0.0 for every 4K run in the final data |
| perf | Counters were gated to the timed region with `perf stat --control`. At most 6 events per run, so no multiplexing (`run_pct` = 100) |
| Tools | Our own tools, since Intel MLC does not support AMD. `latency` (pointer chase), `bandwidth` (multi-thread R/W/mix), `mlp` (independent chains + loaded latency), `kernel_miss`, `tlb` — all in `src/` |

## 2. Hypotheses (stated before the runs)

1. Latency steps up at 48 KiB, 1 MiB and 32 MiB. The L3 edge sits at 32 MiB (one CCD) rather than the
   64 MiB total, because a thread only uses its own CCD's L3.
2. DRAM bandwidth should be well below the theoretical peak and need several cores to saturate.
   (This turned out **wrong** on this machine: see §5.)
3. Writes cost about twice their size in DRAM traffic, because of write-allocate (read-for-ownership).
   Non-temporal stores should avoid that.
4. Raising the number of outstanding misses raises throughput linearly (Little's Law, with latency
   fixed) up to a knee. Past the knee, latency grows with no gain in throughput.
5. With 4 KiB pages, large random footprints pay a page walk on most accesses. Huge pages remove that.

## 3. Zero-queue latency per level

Figure: `figures/final/latency_working_set.png`. Table: `data/processed/final/latency/zero_queue_table.csv`.

A random pointer chase visits each cache line once per lap (Sattolo cycle), so no two loads can overlap.
Each level is measured at a size well inside it (16 KiB, 768 KiB, 16 MiB, 1 GiB).

| Level | Huge pages (ns) | Huge pages (cycles @ 5.70 GHz) | 4K pages (ns) | 4K pages (cycles) |
|---|---|---|---|---|
| L1 | 0.702 | **4.0** | 0.702 | 4.0 |
| L2 | 2.458 | **14.0** | 3.426 | 19.5 |
| L3 | 8.283 | **47.3** | 9.702 | 55.3 |
| DRAM | 99.06 | **566** | 110.27 | 629 |

IQRs are under 1% of the median for every entry. The huge-page column is the true cache latency. The
extra time with 4K pages is address translation: L1 dTLB misses from L2 sizes upward, and page walks for
DRAM-size buffers (see §8). The 4 / 14 / 47-cycle values match AMD's published Zen 5 figures.

**Working-set sweep:**

- **The steps fall exactly at the predicted boundaries:** 48 KiB, 1 MiB and 32 MiB. The L3 → DRAM step
  sits between 32 and 48 MiB, which confirms that the L3 a thread can use is the 32 MiB of its own CCD.
- **A sequential chase stays near 0.7 ns up to 32 MiB** and only reaches 1.2 ns in DRAM. The
  prefetchers hide nearly all latency for predictable addresses, so a sequential test is not a latency
  test.

## 4. Pattern and stride sweep

Figures: `figures/final/latency_pattern_stride.png`, `bandwidth_pattern_stride.png`.

**Latency** (ns per dependent access, huge pages):

| Footprint | seq 64 B | seq 128 B | seq 256 B | seq 1024 B | random (any stride) |
|---|---|---|---|---|---|
| 256 KiB (L2) | 0.72 | 0.71 | 0.72 | 0.76 | 2.46 |
| 8 MiB (L3) | 0.71 | 0.72 | 0.78 | 1.25 | 7.9–8.8 |
| 512 MiB (DRAM) | 1.22 | 2.39 | 2.25 | 4.43 | 97.6–100.1 |

**Bandwidth**, read-only, 1 GiB buffer per thread (DRAM):

| Pattern | Stride | 1 thread, useful GB/s | 8 threads, useful GB/s |
|---|---|---|---|
| seq | 64 B | **55.3** | 47.8 |
| seq | 128 B | 28.3 | 41.1 |
| seq | 256 B | 28.3 | 37.8 |
| seq | 1024 B | 13.6 | 21.4 |
| random | 64 B | 13.4 | **43.1** |
| random | 1024 B | 11.4 | 23.1 |

At 512 KiB per thread (L2-resident), reads reach 181–213 GB/s on 1 thread and 1424–1628 GB/s on
8 threads. That scales almost linearly, because each core has its own L2.

Interpretation:

- **Stride 128 B gives exactly half the useful bandwidth of stride 64 B on one thread.** Touching every
  other line still makes DRAM move about the same number of bytes: the L2 "adjacent line" prefetcher
  fetches 128-byte pairs. The wasted half shows up as lost useful bandwidth. At 1024 B stride only one
  line in 16 is used, and the per-line cost (page crossings, prefetcher restarts) dominates.
- **Random access needs concurrency.** One thread reaches only 13.4 GB/s with random 64 B lines, because
  random lines get no prefetch, so the core's limited number of outstanding misses caps throughput.
  Eight threads reach 43 GB/s.
- **Eight sequential streams are slower than one** (47.8 vs 55.3 GB/s). With 8 interleaved streams,
  consecutive DRAM requests more often hit different rows in the same bank. Fewer row-buffer hits waste
  DRAM cycles. One sequential stream already gets about 96% of the 57.6 GB/s peak, so extra threads add
  only contention.
- **8-byte vs 64-byte access** (`access` column in `pattern/bandwidth.csv`): touching 8 B per line
  instead of the whole line leaves the line bandwidth unchanged (55.5 GB/s) but cuts useful bandwidth
  8×. DRAM always moves whole 64-byte lines.

## 5. Why DRAM bandwidth does not grow with threads

| Threads (1 GiB each, seq read) | GB/s |
|---|---|
| 1 | 53–55 |
| 2 | 53–55 |
| 4 on one CCD | 52.6 |
| 4 + 4 on both CCDs | 54.9 |

These figures come from the reviewer's verification runs on an idle machine. The final 8-thread sequential
point was 47.8 GB/s (§4).

Hypothesis 2 is **rejected for this machine**:

- **One core already reaches about 95% of the theoretical peak**, because the DIMMs run at 3600 MT/s.
  With four DIMMs in two channels, the firmware drops the speed below their 4800 MT/s rating.
- **The link from a CCD to memory is not the limit:** about 64 GB/s for reads, which is above the DRAM
  peak. DRAM itself is.
- **On a platform with faster memory**, e.g. 2 DIMMs at 6000 MT/s (96 GB/s), we would expect the classic
  picture: one core stops at about 50–60 GB/s and several cores are needed to saturate.

## 6. Read/write mix

Figures: `figures/final/bandwidth_rwmix.png`, `loaded_latency_rwmix.png`.

Sequential, 256 MiB per thread. "Program" GB/s counts the bytes the code reads and writes. "Est. DRAM"
adds one read-for-ownership line for each line written with normal stores. The reviewer verified with
the `ls_any_fills_from_sys` counter that normal stores trigger exactly one fill per line written and
non-temporal (NT) stores about zero.

| Mix (R:W) | Stores | 1 thread, program | 1 thread, est. DRAM | 8 threads, program | 8 threads, est. DRAM |
|---|---|---|---|---|---|
| 100% R | — | **57.4** | 57.4 | 47.9 | 47.9 |
| 100% W | normal | 21.2 | 42.3 | 22.3 | 44.5 |
| 100% W | NT | 27.8 | 27.8 | **46.0** | 46.0 |
| 70/30 | normal | 39.1 | 50.8 | 33.1 | 43.1 |
| 70/30 | NT | 49.6 | 49.6 | 43.1 | 43.1 |
| 50/50 | normal | 30.7 | 46.0 | 28.3 | 42.5 |
| 50/50 | NT | 53.5 | 53.5 | 44.9 | 44.9 |

- **Write-allocate is real and costly (Hypothesis 3 confirmed).** 100% normal writes reach only
  21–22 GB/s of program data, but about 42–45 GB/s of DRAM traffic. Every written line is first read.
- **NT stores remove the read, but a single thread cannot exploit it** (27.8 GB/s). With 8 threads NT
  writes reach 46 GB/s, 2.1× normal stores.
- **Mixed traffic loses to read-only.** Even with NT stores, mixes reach at most 49.6 GB/s on one thread
  against 57.4 for pure reads. The DRAM bus must turn around between reads and writes, which costs
  cycles.

**Latency under a mix.** With 7 background threads streaming at full speed, an idle-latency probe
(94.6 ns unloaded) sees:

| Background mix | Probe latency (ns) | Background program GB/s |
|---|---|---|
| 100% R | 239 | 49.0 |
| 70/30 | 275 | 34.2 |
| 50/50 | 272 | 28.7 |
| 100% W | **302** | 22.5 (≈45 DRAM) |

Write-heavy traffic delays reads the most per useful byte: write drains block the bus, and each written
line also costs a read.

## 7. Intensity sweep: throughput vs latency, the knee, and Little's Law

Figures: `figures/final/intensity_mlp.png`, `intensity_loaded_latency.png`.

**Method A: memory-level parallelism (MLP).** Each thread follows K independent random pointer chains
over 256 MiB, interleaved, so up to N = threads × K misses can be in flight. Each chain is still
serial, so the measured time per hop is the true loaded latency.

| Outstanding N | Latency (ns) | Throughput (GB/s) |
|---|---|---|
| 1 | 94.7 | 0.68 |
| 8 | 105.8 | 4.84 |
| 32 (4 × 8) | 113.5 | 18.0 |
| 64 (4 × 16) | 129.0 | 31.7 |
| **128 (4 × 32)** | **193.9** | **42.2** ← knee |
| 192 (4 × 48) | 287.1 | 42.8 |
| 256 (4 × 64) | 382.4 | 42.8 |
| 512 (8 × 64) | 765.5 | 42.8 |

- **Below the knee, Little's Law holds with almost no queueing.** The no-queueing prediction is
  N × 64 B / R₀, with R₀ = 95 ns measured separately. It predicts 21.6 GB/s at N = 32 against 18.0
  measured, and 43 GB/s at N = 64 against 31.7 measured. Latency rises only 1.4× up to N = 64.
- **The knee is about 128 outstanding lines, 42 GB/s, 194 ns.** If latency stayed at 95 ns, 42 GB/s
  would need only 63 lines in flight (42 GB/s × 95 ns / 64 B). In practice it takes about 128, because
  latency has doubled by then.
- **Past the knee, throughput is flat at 42.8 GB/s while latency grows linearly with N** (383 ns at 256,
  766 ns at 512). This is the queueing regime: extra requests only wait.
- **Random chasing saturates at about 43 GB/s, below the 55 GB/s of a sequential stream,** because
  random lines have no DRAM row-buffer locality and no prefetch.
- **A single core reaches only 25.5 GB/s, even with 64 chains** (latency 161 ns). That is the per-core
  limit on outstanding misses, so random traffic needs several cores to reach the knee.

**Method B: loaded latency, as Intel MLC measures it.** One probe thread chases pointers while 7 threads
stream reads, each pausing for a configurable delay between accesses.

| Background delay | Background GB/s | Probe latency (ns) | Inferred lines in flight (BW × lat / 64 B) |
|---|---|---|---|
| 10 000 | 0.24 | 95.2 | 0.4 |
| 320 | 5.8 | 96.4 | 8.7 |
| 160 | 11.4 | 99.7 | 17.8 |
| 80 | 27.9 | 108.5 | 47.3 |
| **40** | **48.1** | **207.3** | **155.8** ← knee |
| 0 | 49.3 | 240.3 | 185.2 |

The second method shows the same shape. Latency stays near 95–110 ns up to about 28 GB/s, then doubles
between 28 and 48 GB/s while bandwidth gains less than 2×. Again the knee is about 150 lines in flight.
For sequential streaming it sits at a higher bandwidth (48 vs 42 GB/s) than for random chains, for the
row-buffer reason above.

## 8. Cache-miss and TLB-miss impact

Figures: `figures/final/kernel_cache_miss.png`, `tlb_miss_impact.png`.

**Cache misses.** Kernel z[i] = x[i] · y[i] on doubles, huge pages. Counters are per element:

| Footprint | Pattern | ns/elem | L1 misses | L2 prefetch misses → L3 | DRAM fills |
|---|---|---|---|---|---|
| 384 KiB (L2) | seq | 0.094 | 0.375 | 0 | 0 |
| 12 MiB (L3) | seq | 0.166 | 0.376 | 0.28 | 0 |
| 3 GiB (DRAM) | seq | **0.729** | 0.380 | 0.003 | **0.211** |
| 12 MiB (L3) | random blocks | 0.174 | 0.384 | 0.011 (demand misses 0.38) | 0 |
| 3 GiB (DRAM) | random blocks | **1.432** | 0.394 | 0 | **0.380** |

- **L1 misses do not predict runtime.** The L1 miss rate jumps from 0 to 0.375 per element at 48 KiB
  (3 arrays × 8 B / 64 B), yet time per element does not change until 1 MiB. The L2 delivers lines
  faster than the loop consumes them.
- **DRAM fills do predict runtime.** Sequential DRAM runs show 0.21 DRAM fills per element. The demand
  rate would be 0.375, so the hardware prefetcher counts some lines elsewhere or merges them. Random
  block order shows 0.38: every line becomes a demand miss with no prefetch. Time doubles
  (0.73 → 1.43 ns per element) as DRAM fills per element almost double.
- **The plain demand-L2-miss counter undercounts streaming code.** In the sequential DRAM run it reads
  only 0.002 per element, because the prefetcher handles the misses. The reviewer added the L2
  prefetch-miss events for this reason. Using demand misses alone would wrongly suggest that the DRAM
  run has almost no misses.

**TLB misses.** One access per 4 KiB page, random page order, 4K vs 2 MiB (THP) pages. Pages are touched
at a random line offset, so cache sets are evenly used.

| Span | 4K: ns | 4K: L2-dTLB misses/access | THP: ns | THP: L1-dTLB misses/access | THP: L2-dTLB misses/access |
|---|---|---|---|---|---|
| 4 MiB | 3.69 | 0.000 | 2.46 | 0.000 | 0.000 |
| 16 MiB | 5.85 | 0.378 | 2.47 | 0.000 | 0.000 |
| 64 MiB | 14.68 | 0.934 | 6.84 | 0.000 | 0.000 |
| 256 MiB | 17.94 | 1.001 | 8.72 | 0.252 | 0.000 |
| 1 GiB | 26.98 | 1.002 | 12.16 | 0.814 | 0.000 |
| 4 GiB | 112.87 | 1.005 | 98.22 | 0.961 | 0.007 |

- **With 4K pages, L2-dTLB misses start at about 8 MiB and reach 1 per access by about 128 MiB.** This
  matches an L2 dTLB of about 4096 entries, i.e. 16 MiB of reach. That is the published Zen 5 size; we
  did not verify it independently. Each miss is a page walk.
- **With huge pages there are no L2-dTLB misses all the way to 4 GiB.** L1-dTLB misses begin between
  192 and 256 MiB, consistent with 96 entries × 2 MiB = 192 MiB.
- **Cost of the page walks:** at 64 MiB–1 GiB, 4K pages are 2.1–2.2× slower than THP at the same
  footprint (14.7 vs 6.8 ns; 27.0 vs 12.2 ns). At 4 GiB both are dominated by DRAM misses on the data
  (1 M distinct lines = 64 MiB > L3), but 4K pages still add about 15 ns per access.
- **Hypothesis 5 confirmed.** The same trend shows in the zero-queue table (§3): 4K pages add 11 ns to
  DRAM latency.

## 9. Benchmark pitfalls demonstrated

Figure: `figures/final/pitfalls.png`. Data: `data/processed/final/pitfall/`.

1. **"DRAM" test that actually measures cache.** A 16 MiB buffer looks large, but it fits in one CCD's
   32 MiB L3:

   | Buffer | Read bandwidth | Chase latency |
   |---|---|---|
   | 16 MiB | 169 GB/s | 8.3 ns |
   | 1 GiB | 55.3 GB/s | 99 ns |

   The small buffer overstates bandwidth 3× and understates latency 12×.
2. **Reading memory that was never written.** Untouched anonymous pages all map to the kernel's shared
   zero page, which stays in cache:

   | Pages | Never written | Pre-faulted |
   |---|---|---|
   | THP | 177 GB/s | 55.3 GB/s |
   | 4K | 185 GB/s | 44.7 GB/s |

   The benchmark never touches DRAM in the "never written" case.
3. **Placing two threads on SMT siblings of one core.** Two threads on CPUs 4 and 20 (same core) against
   CPUs 4 and 5 (two cores):

   | Per-thread buffer | Same core | Two cores |
   |---|---|---|
   | 16 KiB | 670 GB/s | 1273 GB/s |
   | 768 KiB | 168 GB/s | 424 GB/s |

   Sharing a core halves L1 bandwidth. At 768 KiB per thread the 1.5 MiB total no longer fits one core's
   L2, so the gap widens to 2.5×.

## 10. Anomalies and open questions

- **4 threads × 16 MiB on one CCD read at 206 GB/s.** That is a 64 MiB working set, twice the CCD's
  32 MiB L3, yet the rate is about 4× DRAM bandwidth (`pitfall/p1_bandwidth.csv`). A plausible
  explanation is that the L3 replacement policy is not strict LRU, so part of each buffer stays resident
  under cyclic access, and the threads' private L2s add 4 MiB. This was not verified with L3 counters.
- **Sequential DRAM bandwidth drops from 55 to 48 GB/s with 8 threads.** We attribute this to DRAM
  row-buffer conflicts between interleaved streams. It could not be confirmed, because uncore (DRAM
  controller) counters need root.
- **Sequential DRAM fills of 0.21 per element vs the 0.375 expected** (§8). Some prefetched lines
  appear to be attributed to other events. We used fills only for relative comparisons.

## 11. Limitations

- **Memory runs at 3600 MT/s** because of the 4-DIMM configuration, so absolute bandwidth numbers are
  specific to this setup.
- **No uncore or DRAM-controller counters** (they need root). DRAM write traffic is inferred from the
  write-allocate check, not measured directly.
- **Boost was on.** Latency in cycles uses the measured clock, 5.70 GHz.
- **The MLP chase uses 64-byte random lines.** Its knee (42 GB/s) differs from that of streaming
  traffic (48 GB/s). Both are reported.

## 12. AI-use note

- Claude Code (Anthropic) wrote all benchmark code, scripts and this findings draft, at the student's
  direction:
  - Claude wrote the initial pointer-chase tool;
  - a Claude Sonnet agent wrote the remaining tools;
  - a Claude Opus agent reviewed them.
- **Fixes made:**
  - The never-written-memory pitfall merged two cases into one median.
  - The L2-miss counter excluded prefetch.
  - The Little's Law panel was circular, since throughput × latency equals N by construction.
  - The zero-queue L2/L3 sizes partly hit the smaller cache.
  - Re-runs silently appended to old data.
  - The "unpinned threads" pitfall showed no effect and was replaced by the SMT-sibling demonstration.
- **Investigated and kept:** the flat multi-thread DRAM bandwidth was traced to the 3600 MT/s memory
  configuration, and kept as a real finding rather than treated as a bug.
- I am responsible for reviewing and understanding all claims above before submission.
