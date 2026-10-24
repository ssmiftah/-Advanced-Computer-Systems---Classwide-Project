# Project 3 — SSD Performance Profiling: Findings

**Data sources:**
- **Final measurements:** `data/raw/` (raw fio JSON), `data/processed/` (parsed tables) and `figures/`.
- **First full run (invalid, kept as evidence):** `data/kyber/` and `figures/kyber/`. It was made with the
  operating system's default I/O scheduler. That scheduler distorted every experiment that kept more than
  one I/O in flight, so this run is reported **only** as the misleading-setup case in §9.

**Statistics:**
- Read points are the mean of 3 repetitions (30 s each after a 5 s ramp). Write points are the mean of 2.
- Error bars are ± one standard deviation across repetitions.
- MB/s means 10⁶ B/s. Latency percentiles are fio completion latency (clat). Mean latency is fio total
  latency (submission + completion), which is what Little's Law needs.

## 1. Setup and safety

| Item | Value |
|---|---|
| SSD | KIOXIA KXG80ZNV1T02 (XG8 series), 1 TB, NVMe, firmware APGA4102. It is the **system drive** |
| Interface | PCIe 4.0 ×4 (16 GT/s × 4 lanes), about 7.9 GB/s usable |
| Target | One 32 GiB regular file (`p3-ssd/testfile.dat`) on ext4 (`noatime`). It covers about 3% of the drive's LBA range. The filesystem was 88% full before the file was created (96% with it) |
| Raw device | **Never used.** A script guard (`scripts/common.sh: guard_target`) refuses `/dev` paths, symlinks, hard links, paths outside `p3-ssd/` and paths containing `:` |
| I/O path | `direct=1` (O_DIRECT, bypassing the page cache) everywhere except the buffered pitfall demo. `ioengine=io_uring`, CPU-pinned to cores 12–15 |
| I/O scheduler | **`none`** for the final run (see §9 for why). Recorded in every run's `env.txt` |
| Data pattern | Incompressible: `refill_buffers` with `buffer_compress_percentage=0`. A zstd pass over the file came out larger than the input |
| Preconditioning | The test file was filled once with a sequential 1 MiB direct write of random data. It is fully allocated, not sparse, so reads never hit unwritten, zero-filled regions |
| Write bounding | Every write job is limited by bytes (`io_size`), not time. The final run wrote **308 GiB**, against an estimate of 307 GiB and a hard cap of 336 GiB |
| Host | Ryzen 9 9950X; CachyOS Linux 7.3.0; fio 3.42 |
| Temperature | Logged at 1 Hz from the drive's sensor (`temp.csv` in each experiment folder). Range 39–77 °C; peak during the block-size sweep |

## 2. Hypotheses (stated before the runs)

1. QD=1 latency will be about 50–100 µs for 4 KiB random reads (NAND read time plus controller
   overhead). Writes will be faster, because the drive acknowledges them from its cache.
2. 4 KiB random-read IOPS will grow almost linearly with queue depth until the controller and NAND
   parallelism saturate, somewhere around QD 32–128. Past that knee, latency will grow with no extra
   throughput, as Little's Law predicts.
3. Sequential bandwidth will saturate at about 5–7 GB/s, below the PCIe 4.0 ×4 ceiling, by 64–128 KiB
   blocks.
4. Sustained writes will drop sharply once the drive's fast SLC write cache fills. That cache will be
   small, because the drive is nearly full.
5. Buffered I/O will inflate read results by serving them from RAM.

## 3. QD=1 latency (zero-queue baselines)

Figure: `figures/qd1_latency.png`. Table: `figures/qd1_latency_table.md`.

| Workload | IOPS | MB/s | Mean µs | p50 µs | p95 µs | p99 µs | p99.9 µs | p99.99 µs |
|---|---|---|---|---|---|---|---|---|
| 4 KiB random read | 16 750 | 68.6 | **59.5** | 50.9 | 80.4 | 81.8 | 84.5 | 174 |
| 4 KiB random write | 55 810 | 228.6 | **17.8** | 15.2 | 23.7 | 25.6 | 42.5 | 7 687 |
| 128 KiB sequential read | 6 063 | 794.7 | 164.7 | 160.8 | 231.1 | 280.6 | 333.8 | 489 |
| 128 KiB sequential write | 17 720 | 2 323 | 55.5 | 44.3 | 67.7 | 110.2 | 503.3 | 14 070 |

- **Reads take about 3× longer than writes at QD=1** (59.5 vs 17.8 µs). A read must fetch from NAND. A
  write is acknowledged as soon as the data reaches the controller's cache, and the NAND program happens
  later.
- **Write tails are long.** Every few thousand writes (p99.99: 7.7–14 ms), a write lands while the
  controller is flushing or garbage-collecting. Read tails stay tight (p99.99 = 174 µs).
- **The run-to-run spread is small** (std 0.04 µs for reads, 1.6 µs for 4K writes). These baselines
  were unaffected by the scheduler problem in §9: at QD=1 there is nothing to throttle. Rerunning QD=1
  in the queue-depth sweep with no scheduler gave the same values within 1%.

## 4. Block-size and pattern sweep

Figures: `figures/bs_sweep_qd1.png`, `figures/bs_sweep_qd32.png`. Throughput and latency come from the same
runs.

At QD=32:

| Block | Random read MB/s (IOPS) | Sequential read MB/s | Random write MB/s | Sequential write MB/s | Random-read mean µs |
|---|---|---|---|---|---|
| 4 KiB | 1 621 (396 k) | 1 732 | 1 636 | 1 519 | 81 |
| 16 KiB | 3 724 (227 k) | 3 857 | 3 160 | 3 327 | 141 |
| 32 KiB | 4 870 (149 k) | **6 326** | 1 929 | 4 986 | 215 |
| 64 KiB | **4 911** (75 k) | 6 248 | 2 045 | 5 316 | 427 |
| 128 KiB | 4 364 (33 k) | 5 716 | 1 647 | 5 289 | 961 |
| 256 KiB | 4 100 (16 k) | 5 573 | 1 829 | 5 316 | 2 046 |
| 1 MiB | — | 5 580 | — | 5 399 | — |

- **Small blocks are limited by IOPS, large blocks by bandwidth.** At 4 KiB the drive does about 400k
  IOPS, which is only 1.6 GB/s. From 32–64 KiB upward reads saturate at 4.4–6.3 GB/s and IOPS fall in
  proportion to block size. Hypothesis 3 is confirmed.
- **The interface is not the ceiling.** The best sequential read is 6.3 GB/s, 80% of the PCIe 4.0 ×4
  limit. The cap comes from the controller and NAND.
- **Latency grows linearly with block size once bandwidth saturates.** Each 2× in block size gives about
  2× in mean latency (215 → 427 → 961 → 2046 µs). At fixed QD and fixed bandwidth, by Little's Law,
  latency must be proportional to bytes per request.
- **Random writes above 16 KiB collapse to about 1.6–2 GB/s, with large variance.** Sequential writes hold
  5.3 GB/s. The drive and filesystem are nearly full, so random writes fragment the controller's free
  space and force garbage collection. Several error bars span ±25%.
- At QD=1 (`bs_sweep_qd1.png`) everything is latency-bound. 128 KiB sequential reads reach only 0.9 GB/s
  and 1 MiB reads 3.1 GB/s. Parallelism, not block size alone, is what fills the drive.

## 5. Read/write mix

Figure: `figures/rwmix.png`. 4 KiB random, QD=32:

| Mix (R/W) | Read IOPS | Write IOPS | Total IOPS | Read mean µs | Read p99 µs | Write mean µs |
|---|---|---|---|---|---|---|
| 100/0 | 400 500 | — | 400 500 | 79.7 | 176.5 | — |
| 70/30 | 283 300 | 121 900 | 405 200 | 101.3 | 274.4 | 26.3 |
| 50/50 | 211 500 | 211 300 | 422 800 | 114.8 | 292.9 | 36.1 |
| 0/100 | — | 424 400 | 424 400 | — | — | 75.2 |

- **Total IOPS stays about the same (400–425k) whatever the mix,** so the bottleneck is the
  controller's command rate rather than the NAND.
- **Mixing writes in hurts reads.** Read mean latency rises 44% (79.7 → 114.8 µs) and read p99 rises
  66% from pure reads to 50/50. Reads wait behind writes and behind background programming.
- **Writes inside a mix look fast** (26–36 µs mean), because they are acknowledged from cache.

## 6. Queue-depth sweep: throughput vs latency, the knee, Little's Law

Figures: `figures/qd_sweep_iodepth.png`, `figures/qd_sweep_numjobs.png`. Table: `figures/littles_law_table.md`.

4 KiB random read, one job, `iodepth` sweep:

| QD | IOPS | Mean µs | p99 µs | IOPS × mean latency |
|---|---|---|---|---|
| 1 | 14 680 | 67.9 | 82 | 1.00 |
| 4 | 58 490 | 68.2 | 107 | 3.99 |
| 16 | 221 200 | 72.2 | 138 | 15.97 |
| 32 | 399 800 | 79.9 | 177 | 31.94 |
| 64 | 624 600 | 102.3 | 264 | 63.91 |
| **128** | **700 600** | **182.5** | 388 | 127.9 ← knee |
| 256 | 700 000 | 365.6 | 575 | 255.9 |

- **Up to QD 32 the drive scales almost linearly.** 27× the QD=1 throughput costs only +18% latency.
  This is the region where the controller still has idle NAND dies to use.
- **The knee is at QD 128 and about 700k IOPS.** From 64 to 128, throughput gains only +12% while
  latency rises +78%. From 128 to 256, throughput is flat and latency doubles exactly. That is the
  textbook saturated queue: by Little's Law, with throughput fixed, latency = N / X, so doubling N
  doubles latency. The knee rule (`plot_qd_sweep.py`) picks QD 128.
- **Random writes knee earlier, at QD 32** (320k IOPS, 101 µs). QD 128 gives no more throughput (311k)
  but 4× the latency.
- **numjobs gives the same curve as iodepth.** Several jobs at QD=1 behave like one job at a high QD,
  e.g. 32 jobs reach 400.0k vs 399.8k. The drive does not care whether its parallelism comes from many
  threads or one deep queue.
- **About the Little's Law check:** IOPS × mean latency equals the configured number of outstanding
  I/Os (ratio 0.985–1.000) at every point. That is expected: fio keeps exactly N requests in flight.
  But it only proves the *host* holds N requests. It does not show that the *device* is working on N in
  parallel. §9 shows a case where this check passed perfectly while the device was serving only 1–6
  requests at a time.

## 7. Tail latency

Figure: `figures/tail_latency.png`. Table: `figures/tail_latency_table.md`. Measured at mid-QD (32) and at
the knee (QD 128):

| Workload | QD | IOPS | p50 µs | p95 µs | p99 µs | p99.9 µs | p99.99 µs |
|---|---|---|---|---|---|---|---|
| 4K random read | 32 | 394 k | 75 | 134 | 179 | 242 | 307 |
| 4K random read | 128 | 698 k | 165 | 293 | 387 | 537 | 717 |
| 70/30 random | 32 | 283 k (reads) | 86 | 197 | 279 | 387 | 834 |
| 70/30 random | 128 | 395 k (reads) | 218 | 352 | 485 | 696 | **3 297** |

- **At the knee every percentile roughly doubles,** but the shape of the distribution stays the same
  (p99.99 / p50 is about 4×). Pure-read queueing spreads latency evenly.
- **Mixing in writes damages the extreme tail most.** At QD 128 the 70/30 p99.99 is 3.3 ms, 4.6× the
  pure-read value, while p50 rises only 1.3×. A few reads get stuck behind write flushes or garbage
  collection. For a latency-sensitive service, the practical operating point is below the knee, and
  write traffic is the main threat to the tail.

## 8. Working set (LBA range) and device state

Figures: `figures/workingset.png`, `figures/sustained_write.png`.

**LBA span**, 4 KiB random, QD=32: span from 1 GiB to 32 GiB within the test file:

| Span | 1 G | 2 G | 4 G | 8 G | 16 G | 32 G |
|---|---|---|---|---|---|---|
| Read k IOPS | 401 | 465 | 429 | 454 | 419 | 405 |
| Write k IOPS | 432 | — | 419 | — | — | 404 |

The span has no systematic effect: values vary ±8% with no trend. The likely reason is that this drive
keeps its whole logical-to-physical mapping table in its onboard DRAM, so a random read pays no extra
mapping lookup however far apart the addresses are. The test file covers only 3% of the drive, so
effects that appear only at full-drive spans could not be tested.

**Sustained write: SLC-cache exhaustion.** This was one 1 MiB sequential write job at QD 16, writing
64 GiB around the test file. Hypothesis 4 is confirmed:

- **About 5.4 GB/s for the first 3 s, then a cliff to about 1.5–1.6 GB/s after about 19 GiB.** That is
  the point where the fast SLC cache is full and writes go straight to slower TLC NAND.
- **A 3-second recovery to 5.4 GB/s around t = 15–18 s,** then back to 1.5 GB/s. The controller
  briefly freed SLC space, probably by moving cached data into TLC in the background.
- **Overall average 2.65 GB/s over 64 GiB, with p99 completion latency 32 ms.**
- **Temperature rose from 58 to 65 °C during the test.** That is far below the throttling range. The
  drop is the cache running out, not thermal throttling.

About 19 GiB of SLC cache is small for a 1 TB drive. That fits the drive being nearly full: dynamic SLC
caches are carved out of free NAND.

## 9. Misleading setups

Figure: `figures/misleading_setup.png`. Table: `figures/misleading_cache_table.md`. Evidence for the
Kyber case is in `figures/kyber/` and `data/kyber/`.

### 9a. The operating system's I/O scheduler throttled the drive

This problem was found in our own first full run. CachyOS sets the **Kyber** I/O scheduler on NVMe
devices by default (`/usr/lib/udev/rules.d/60-ioschedulers.rules`). Kyber limits how many requests it
dispatches to meet a latency target (2 ms for reads). Our first run used Kyber, and its results looked
plausible at first sight.

Symptoms:

- **Throughput stuck at whole multiples of the QD=1 rate.** Many runs landed on 14.4k IOPS, 29.2k, 44k or
  87.1k: 1, 2, 3 and 6 times the QD=1 rate of about 14.5k. That is what one would see if the device were
  serving only 1, 2, 3 or 6 requests at a time while the rest waited on the host.
- **Repeats of the same configuration disagreed by 5×.** QD 64 gave 220k, then 177k, then 44k IOPS.
- **The QD sweep was non-monotonic** (QD 32: 220k; QD 128: 142k; QD 256: 314k).
- **Little's Law still held exactly** (eff/cfg = 0.997–1.000), because the waiting happened on the host
  and fio counts host queueing in latency.

Kyber run vs final run (no scheduler), same configurations:

| Configuration | Kyber IOPS | No scheduler IOPS | Ratio |
|---|---|---|---|
| 4K random read QD 32 (block-size sweep) | 34 400 | 395 600 | **11.5×** |
| 4K random read QD 32, 1 GiB (pitfall demo) | 14 400 | 390 600 | **27.1×** |
| 4K random read QD 128 | 142 100 | 700 600 | 4.9× |
| 4K random read, 32 jobs | 87 100 | 400 000 | 4.6× |
| 4K random read, span 4 GiB | 15 700 | 429 200 | **27.3×** |
| 4K random write QD 32 | 157 700 | 320 400 | 2.0× |
| QD = 1 (any) | 14 470 | 14 680 | 1.01× |

**Confirming the cause.** Two read-only 8-second tests were run back to back on the same file. The first,
with Kyber, gave 37k IOPS at QD 32 for both `io_uring` and `libaio`, which rules out the I/O engine.
After switching the scheduler to `none`, the second gave **515k IOPS**. QD=1 did not change (53 µs).

**Lessons:**

- **The software stack between fio and the drive must be recorded and controlled.** The scheduler is
  now set to `none` by `common/bench_mode.sh`, and every run's `env.txt` records it.
- **Little's Law agreement is not a test of device concurrency.**
- **A curve that suddenly gets worse with more parallelism is a red flag** to investigate, not a result.

**What Kyber did not affect:** the sustained sequential write gave the same average with and without
Kyber (2.62 vs 2.53 GB/s). We had expected Kyber to have throttled it and reran it to check. Large
sequential writes at QD 16 apparently stayed under Kyber's 10 ms write target.

### 9b. Buffered I/O: reads come from RAM

With `direct=0`, the page cache deliberately warmed first, and `invalidate=0` (fio would otherwise drop
the cache):

| Workload | Direct (real device) | Buffered | Inflation |
|---|---|---|---|
| 4K random read, 1 GiB span | 391k IOPS, 81.8 µs | **1.98M IOPS, 16.1 µs** | 5.1× |
| 128K sequential read | 6.75 GB/s | **39.0 GB/s** | 5.8× |
| 4K random write | 444k IOPS | 264k IOPS | 0.6× (slower) |

- **Buffered reads report 39 GB/s,** five times what a PCIe 4.0 ×4 link can physically carry. That
  number is DRAM bandwidth, not SSD bandwidth.
- **Buffered random writes are slower than direct ones.** Each write goes through page-cache
  bookkeeping and later writeback instead of straight to the device.

### 9c. Wrong effective queue depth

`ioengine=psync` with `iodepth=32` gives 14 580 IOPS at 69.7 µs, the same as QD=1 (14 570 IOPS). A
synchronous engine ignores `iodepth`, so the "QD 32" label is false. The same QD 32 with `io_uring` gives
396k IOPS.

## 10. Anomalies and open questions

- **Sequential read peaks at 32–64 KiB blocks (6.3 GB/s), not at 1 MiB (5.6 GB/s).** At 1 MiB the p99
  latency is 47 ms, against 1.3 ms at 128 KiB. Large requests may be split inside the drive (Linux
  limits a single request to 128 KiB on this device: `max_hw_sectors_kb = 128`), and the pieces then
  queue unevenly. Not investigated further.
- **The short SLC recovery during the sustained write** (§8) is not explained. The controller's
  background policy is not visible from the host.
- **QD=1 4K random-read latency is 59.5 µs in the QD=1 experiment but 67.9 µs inside the QD sweep.**
  The two measurements were taken an hour apart, in different drive states: the sweep ran after about
  100 GiB of writes. That suggests background garbage collection adds about 8 µs, but this was not
  isolated.

## 11. Limitations

- **Filesystem, not raw device.** The SSD is the system drive, so all tests target a file on ext4.
  O_DIRECT bypasses the page cache, but the filesystem's extent lookups remain, and the file covers only
  3% of the LBA space. Full-drive preconditioning (the usual steady-state method) was not possible.
- **Short write windows.** Write points are bounded by bytes (4 GiB per job) to limit wear. Fast
  sequential writes therefore run for only about 1 s, which is thin for p99.99.
- **Two write repetitions vs three for reads,** again to limit wear.
- **No SMART data.** `nvme smart-log` needs root. Temperature came from sysfs, and no throttling flags
  were read.
- **Total wear from this project:**

  | Source | Writes |
  |---|---|
  | Test-file fill | 32 GiB |
  | Kyber run | about 320 GiB |
  | Final rerun | 308 GiB |
  | An over-budget probe during code review (documented in REPORT_NOTES.md) | about 88 GiB |
  | **Total** | **about 0.75 TB** |

  That is small against a client drive's rated endurance, typically hundreds of TB written.

## 12. AI-use note

- Claude Code (Anthropic) wrote all scripts, fio configs, parsers, plotting code and this findings
  draft, at the student's direction:
  - a Claude Sonnet agent wrote the initial code;
  - a Claude Opus agent reviewed it.
- **Fixes made:**
  - Redesigned the write plan from a multi-TB, time-bounded plan to byte-bounded jobs.
  - Closed two holes in the safety guard (`:` in paths, hard links).
  - Fixed the buffered-I/O demo (fio's default `invalidate=1` had dropped the cache).
  - Fixed knee ordering for the tail experiment, plus several parser and plot bugs.
- **Over-budget write:** AI wrote about 88 GiB against a 15 GiB budget, because it
  wrongly assumed `io_size` caps a `time_based` fio job. That mistake led to the byte-bounded design.
- **The Kyber problem** was caught when Claude inspected the first full run's results, which showed the
  whole-multiple pattern in §9a. It was confirmed with controlled read-only tests before any rerun.
- **What I did:** decided the write budget, ran the I/O-heavy runs, approved the rerun, and made minor fixes made by the coding agent.
- I am responsible for reviewing and understanding all claims above before submission.
