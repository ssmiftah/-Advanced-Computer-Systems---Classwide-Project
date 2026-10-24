# Sanity observations (QUICK mode, 2 GiB file, 4 s jobs, 1 rep; NOT final data)
- QD1 4K randread: mean ~53-55 us, p50 49 us, p99 ~80 us, ~18.8k IOPS.
- 4K randread QD32: ~445k IOPS (mean 72 us); iodepth 256: ~457k IOPS, mean 560 us (saturation near QD64).
- 128K seq read QD1: ~1.0 GB/s; QD32 ~5.7 GB/s (file small, may be partly controller-cache friendly).
- Little's Law holds for reads (eff/cfg ~0.997-0.999). Write points in QUICK mode are 64 MiB jobs (startup-dominated), so ignore their bandwidth.
- Unthrottled probes (reviewer): 4K randwrite QD1 51k IOPS/19 us (write cache), QD32 335k IOPS; 128K seq write QD1 2.6 GB/s;
  1M seq write QD32 5.3 GB/s averaged over ~55 GiB/10 s (no visible SLC exhaustion within that volume). PCIe Gen4 x4 link.
- Buffered 4K randread on 1 GiB span: ~1.6-1.9M IOPS vs 441k direct (page cache). Buffered 128K seq read was NOT faster in the
  writer's first sanity run because fio's default invalidate=1 drops the page cache (28 GiB of device reads in 4 s); with
  invalidate=0 + warm-up: 38 GB/s buffered vs 7.1 GB/s direct. Buffered 4K randwrite via io_uring (no fsync) was SLOWER than
  direct (131k vs 256k IOPS, QUICK) -- io_uring punts buffered writes to worker threads.
- psync with iodepth=32 behaves as QD1.
- NVMe temp idle ~37-41 C. No SLC-cache/throttling observable in the 8 s capped sanity run (expected).
- Tail plots show ~1 ms outliers at p99.99 (maybe other processes / GC); verify with full runs.

## Over-budget write during code review (2026-10-23)
While reviewing this code, the reviewer agent ran a 10 s, 1 MiB, QD32 sequential-write probe with
`time_based=1` and `io_size=1G`, assuming `io_size` would cap the job. fio ignores `io_size` for
time-based jobs, so the probe wrote about 58 GiB; that review session wrote about 88 GiB in total,
against a 15 GiB budget (measured from `/sys/block/nvme0n1/stat`). Since then every write job is
byte-bounded (`time_based=0`, `io_size` cap; `runtime` acts only as a maximum).

## Kyber I/O scheduler invalidated the first full run (2026-10-23)
See FINDINGS.md §9a. The first full run is archived in `data/kyber/` and `figures/kyber/`; the final
data was re-collected with the scheduler set to `none`.
