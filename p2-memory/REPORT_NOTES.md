# Sanity observations (NOT final data; shared machine, cpus 4-7, short runs)

- Core clock while chasing: ~5.5-5.65 GHz (in-process cycles/time agrees with perf stat: 5.651 GHz). Nominal-clock conversion would be wrong.
- Latency (random chase, THP): L1 16 KiB 0.72 ns = 4.0 cycles; L2 512 KiB ~2.5-2.8 ns = 14-16 cyc; L3 8 MiB ~8.4 ns (THP) / 10.1 (4k) = 47-56 cyc; DRAM 256 MiB ~103 ns (THP) / 115 ns (4k) = 570-630 cyc.
- Read bandwidth, 1 thread (GB/s): 16 KiB ~540-640; 32 MiB (L3-ish) ~155; 256 MiB-1 GiB DRAM ~52-56.
  Multi-thread DRAM sequential read does NOT scale: 2 thr ~50, 4 thr (one CCD) ~47-48, 8 thr (2 CCDs) ~46.6, 16 thr ~45.8 GB/s. Total ~47-56 GB/s looks low for DDR5 dual channel
  (single thread already reaches the plateau); possibly memory clock config, concurrent load from other agents, or DRAM page conflicts from identical buffer phase. Worth checking under quiet conditions before the final run.
- Cached multi-thread reads scale: 4 x 4 MiB ~665 GB/s; 4 x 16 MiB (64 MiB total on one CCD) ~185-200 GB/s.
- 100% W, normal stores: ~21 GB/s program bytes (est. DRAM traffic ~42 GB/s with write-allocate); NT stores 27.7 GB/s; 7:3 mix ~38 GB/s; random 1:1 ~12 GB/s.
- 8 B access at stride 256: 3.5 GB/s useful vs 28 GB/s of line traffic.
- MLP (256 MiB, THP): K=1 98 ns, 0.65 GB/s; K=8 109 ns, 4.7 GB/s; K=16 116 ns, 8.9 GB/s; K=32 130 ns, 15.8 GB/s; K=64 167 ns, 24.5 GB/s;
  4 threads x 16 chains 131 ns, 31 GB/s (64 outstanding). A single thread keeps scaling past K=32, so per-core fill-buffer limit is not hit before K=64 on this chase.
- Loaded latency: probe 98 ns idle -> 104 ns with light background (3.5 GB/s) -> 216 ns with 3 streamers at full speed (50.6 GB/s).
- Pitfalls reproduce: untouched ("nowarm") 256 MiB read = 175 GB/s vs 53 GB/s pre-faulted; 16 MiB "DRAM" test = 168 GB/s vs 53 GB/s real. Unpinned vs pinned showed NO visible difference at 4 threads (scheduler left them in place) -- the pinning pitfall needs oversubscription / background load to show; consider adding load or more threads than cores.
- TLB (stride 4096, random page order, 1 node/page): 32 MiB span: 4k 10.4 ns vs THP 3.2 ns; 512 MiB: 26 vs 12 ns; 4 GiB: 114 vs 101 ns (cache misses dominate). perf: 4k, 512 MiB: ~1.0 L2-dTLB misses (page walks) per access; THP ~0.
- Kernel z=x*y: L1d misses/elem 0.375 once footprint > L1 (3 arrays, one miss per 8 doubles each), DRAM fills/elem ~0.2 at 384 MiB. `l2_cache_req_stat.ic_dc_miss_in_l2` (demand-only) stays small for the streaming kernel because prefetchers cover it.
- `perf stat --control` prints "Events enabled/disabled" on stderr; harmless.

## Review findings (independent check)
- DRAM read plateau is REAL, not a benchmark bug: 4 x 16 GiB Micron CT16G48C40U5 (DDR5-4800, single rank) = 2 DIMMs per channel,
  configured at 3600 MT/s (DMI type 17 via `inxi -m`; confirm with `sudo dmidecode -t memory`). Peak = 2 ch x 8 B x 3.6 GT/s = 57.6 GB/s.
  Measured (quiet moment, 1 GiB/thread, seq read): 1T 53-55, 2T 53-55, 4T one CCD 52.6, 2+2 across CCDs 52-55, 4+4 across CCDs 54.9 GB/s
  = ~95% of peak, so one core already saturates DRAM (its CCD link, ~32 B/FCLK ~ 64 GB/s, is above the DRAM peak). Background I/O from
  other jobs (fio) dropped single-run results to ~46 GB/s -> collect final data on a quiet machine.
- Write-allocate verified with perf: 100% normal 64 B stores -> ls_any_fills_from_sys.all == lines written (1 RFO per line); --nt -> ~0 fills.
- l2_cache_req_stat.ic_dc_miss_in_l2 excludes L2 HW prefetch; kernel set A now also counts l2_pf_miss_l2_hit_l3 / l2_pf_miss_l2_l3.
  ls_any_fills_from_sys.local_ccx under-counts L3 traffic (L2-prefetched lines are later L1 fills "from L2"); dram_io_all matched 97% of
  lines read in a 1 GiB stream.
- Pitfall P3 replaced: 2 threads on SMT siblings (cpus 4,20) vs 2 cores (4,5): 16 KiB/thread 665 vs 1275 GB/s, 768 KiB/thread 166 vs 430 GB/s.
