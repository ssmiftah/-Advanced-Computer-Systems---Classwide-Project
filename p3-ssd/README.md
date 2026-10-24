# Project 3: SSD performance profiling (fio)

## Safety (read first)
- Target SSD (KIOXIA KXG80ZNV1T02) is the **system drive**. All I/O goes to ONE regular file, `p3-ssd/testfile.dat`
  (gitignored). Never a `/dev/*` path. `scripts/common.sh:guard_target` refuses devices, symlinks, directories, and any
  path outside `p3-ssd/` or not named `testfile*`; fio jobs also run with `allow_file_create=0`.
- `prepare_testfile.sh` refuses if fewer than `size + 10 GiB` would remain free (`MIN_FREE_GIB`).
- No sudo needed; no system settings are changed. `nvme smart-log` is attempted and skipped if not permitted.
  Temperature comes from `/sys/class/nvme/nvme0/hwmon0/temp1_input` (1 Hz logger, `temp.csv` per experiment).
- The guard also refuses paths containing `:` (fio's `filename=` splits on `:` and would open other, relative
  files), `\`, newline/tab, and files with more than one hard link (a hard link could alias a user file). `TESTFILE` is
  canonicalised (`realpath`) once, so fio opens exactly the path the guard checked. Spaces in the repo path are fine.
- Delete the file when done: `scripts/cleanup.sh`.

## How to run (from the repo root)
```
bash p3-ssd/scripts/run_all.sh --estimate     # print duration + write-volume estimate only
bash p3-ssd/scripts/run_all.sh                # prepare file, run exp 1-7 (asks for confirmation; --yes skips)
bash p3-ssd/scripts/plot_all.sh               # parse_fio.py + all plot_*.py -> data/processed, figures/
bash p3-ssd/scripts/cleanup.sh
```
Individual: `prepare_testfile.sh`, `run_qd1.sh`, `run_bs_sweep.sh`, `run_rwmix.sh`, `run_qd_sweep.sh`, `run_tail.sh`
(run after plotting exp 4 so the knee QD is picked up from `data/processed/knee.txt`), `run_workingset.sh`,
`run_sustained.sh`, `run_misleading.sh`, optional `run_pattern.sh` (compressible-data check, not in run_all).
All take `--yes`/`--estimate`. `QUICK=1` gives a tiny sanity configuration (2 GiB file, 4 s read jobs, 64 MiB per
write job, 1 rep, ~4 GiB written in total) whose output goes to `p3-ssd/scratch/sanity/{raw,processed,figures}`
(gitignored; `plot_all.sh`/`parse_fio.py` honour `QUICK=1` too) -- QUICK write numbers are startup-dominated, not results.
Output otherwise goes to `RAW_DIR` (default `data/raw`), `PROC_DIR`, `FIG_DIR` (env-overridable).
Knobs: `TESTFILE_SIZE` (32G), `RUNTIME` (30), `RAMP` (5), `REPS` (3), `COOLDOWN` (20 s between experiments),
`CPUS_SINGLE` (12), `CPUS_MULTI` (12-15), `ENGINE` (io_uring, libaio fallback), sweep lists `BS_RAND BS_SEQ BS_QDS QD_LIST JOBS_LIST QD_OPS
RWMIX_LIST WS_SPANS WS_W_SPANS QD_W_LIST JOBS_W_LIST BS_W_QDS TAIL_QDS SUST_GIB W_IO_CAP W_RUNTIME W_REPS ...` (see header of each script).

## Fixed settings in every run (`configs/base.fio`)
direct=1 (except exp 7), io_uring, reads: time_based (`RUNTIME` 30 s, `RAMP` 5 s excluded from stats, `REPS` 3);
**write-containing jobs: size-bounded** (see "Write volume" below), group_reporting, json+ output,
random offsets aligned to bs (`norandommap=1`, may revisit blocks), pinned CPUs, repeats `REPS` (std reported).
**Data pattern: incompressible** (`refill_buffers=1`, `randrepeat=0`, `buffer_compress_percentage=0`) for the
precondition fill and every run; `run_pattern.sh` varies it explicitly.
**Precondition:** sequential 1 MiB direct write of the whole file with random data (+`end_fsync`); the script verifies
allocated bytes >= file size, so reads never hit sparse/unwritten extents. Optional `PRECOND_RAND_GIB=N` adds 4K random writes.

## Experiments: fixed vs varied
| # | script | varied | fixed |
|---|---|---|---|
| 1 | run_qd1 | 4K randR/W, 128K seqR/W | QD1, 1 job |
| 2 | run_bs_sweep | bs (rand 4-256K, seq 4K-1M), op, QD in {1,32} | full span |
| 3 | run_rwmix | 100R/70-30/50-50/100W | 4K random, QD32 |
| 4 | run_qd_sweep | iodepth 1..256 (1 job); numjobs 1..64 (iodepth 1); randread+randwrite | 4K, full span |
| 5 | run_tail | QD (mid=knee/4 >= 4, knee from exp 4 -- run_all computes it right after exp 4), randread and 70/30 | 4K, 60 s, percentiles + CCDF from json+ bins |
| 6a | run_workingset | span 1..32 GiB of file | 4K random QD32 |
| 6b | run_sustained | time, up to SUST_GIB=64 GiB written | 1M seq write QD16, wraps over file; bw logged per second + temperature |
| 7 | run_misleading | direct 0/1 on 1 GiB span; psync+iodepth32 vs io_uring | buffered runs: `invalidate=0` + explicit warm-up read (fio's default invalidate=1 drops the page cache, so buffered seq reads silently hit the SSD); fincore log |

Knee heuristic (plot_qd_sweep.py): last N before the first step where throughput gain < 10% and mean latency growth
> 25% (`KNEE_GAIN`, `KNEE_LAT`); fallback: smallest N reaching 95% of peak. Little's Law: effective N = total IOPS x mean total latency,
tabulated against configured iodepth x numjobs (`figures/littles_law_table.*`).
Units: MB/s = 1e6 B/s, MiB/s = 2^20 B/s (both stored). Percentiles are completion latency (clat); mean is submission+completion (lat).

## Write volume / duration of full run_all (defaults) -- SSD wear budget
The SSD is the system drive, so every job that writes is **bounded by bytes, not time** (no rate caps, which would
distort throughput/latency): `time_based=0`, `io_size=W_IO_CAP` (default **4 GiB per job+rep**, split over numjobs),
`runtime=W_RUNTIME` (10 s) only as a maximum, `W_RAMP=0`, `W_REPS=2`. fio counts ramp IOs toward `io_size`, so the cap
is exact (verified with /sys/block/nvme0n1/stat). Note: fio IGNORES `io_size`/`number_ios` when `time_based=1`.
Measured windows: 4K random QD32 ~3 s (~1M IOs), 1M sequential ~0.8 s (4096 IOs), 4K QD1 10 s.
Write points are also thinned: block-size sweep writes only at QD32 (`BS_W_QDS`), QD sweep writes on
`QD_W_LIST="1 2 4 8 16 32 128"` / `JOBS_W_LIST="1 4 16"`, working-set writes on `WS_W_SPANS="1G 4G 32G"`.
Sustained write (exp 6b) is size-bounded: `SUST_GIB` (default **64 GiB**, wraps over the file), `SUST_MAX_RUNTIME` 900 s.

`run_all.sh --estimate` prints per experiment the time, the EXPECTED volume (write-bandwidth model calibrated on this
drive: 4K QD1 51k IOPS, 4K QD32 335k IOPS, 1M QD32 5.3 GB/s; `EST_*`) and the HARD worst case (sum of the caps). Defaults:

| | time | expected | worst case |
|---|---|---|---|
| test-file fill (32 GiB) | <1 min | 32 GiB | 32 GiB |
| exp 1-5, 6a, 7 | ~2 h | ~255 GiB | ~288 GiB |
| exp 6b sustained | ~15 s - few min | 64 GiB | 64 GiB |
| **total** | **~2.0 h** | **~351 GiB** | **~384 GiB** |

run_all prints this and asks for confirmation (`--yes` skips); at the end it prints device-level writes measured
from `/sys/block/nvme0n1/stat`. Reduce with `W_IO_CAP=2G`, `W_REPS=1`, `SUST_GIB=...`; raising them raises the bound
linearly. (The buffered-write demo additionally causes page-cache writeback of at most its 4 GiB cap.)

## Limitations
- Test file on ext4, not the raw device: filesystem/journal/page-cache effects exist (direct=1 bypasses cache); the 32 GiB file
  covers only ~3% of the LBA space, so GC/SLC behaviour of a nearly-full drive is only partially exercised.
- Write jobs on ext4 can show rare ~8 ms completion stalls (seen in QUICK runs at p99.9+ of 128K QD1 writes and of reads
  in 70/30 mixes); plausibly jbd2/inode-timestamp journalling, i.e. a filesystem effect, not the SSD. Mention it when
  discussing write/mixed tails.
- numjobs > 4 oversubscribes the 4 pinned CPUs (12-15); size-bounded write jobs with numjobs>1 finish at slightly different times.
- Shared system drive (89% full): background I/O by other processes adds noise; thermal state carries over between runs.
- Writes through the filesystem overwrite in place (ext4); SSD-internal remapping is invisible to us.
