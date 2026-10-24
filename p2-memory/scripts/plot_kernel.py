"""Exp 6: cache-miss impact on z=x*y; Exp 7: TLB-miss impact."""
from plot_common import *

a = args()
d = load(a, "kernel", "kernel_joined.csv")
if d is not None:
    d = d.assign(cfg=d.kernel + ", " + d.pattern + ", stride " + d.stride_blocks.astype(str) + " blk")
    fig, axs = plt.subplots(1, 3, figsize=(15, 4.4))
    pf = [c for c in ("l2_pf_miss_l2_hit_l3.l1_dc_l2_hwpf_per_work", "l2_pf_miss_l2_l3.l1_dc_l2_hwpf_per_work") if c in d]
    d["l2_pf_miss_per_work"] = d[pf].sum(axis=1, min_count=1) if pf else np.nan
    ev = [("L1-dcache-load-misses_per_work", "L1d load misses"),
          ("l2_cache_req_stat.ic_dc_miss_in_l2_per_work", "L2 demand misses (excl. HW prefetch)"),
          ("l2_pf_miss_per_work", "L2 HW-prefetch misses (to L3 or DRAM)"),
          ("ls_any_fills_from_sys.dram_io_all_per_work", "L1d fills from DRAM")]
    for i, (c, g) in enumerate(d.groupby("cfg", sort=False)):
        g = g.sort_values("footprint")
        errline(axs[0], g.footprint, g.ns_per_elem_median, g.ns_per_elem_q1, g.ns_per_elem_q3, c, i)
        for j, (col, lab) in enumerate(ev):
            axs[1].plot(g.footprint, g[col].clip(lower=1e-6), marker=MARKERS[j], color=COLORS[j], ls="-" if i == 0 else ":",
                        label=f"{lab}" if i == 0 else None, ms=4)
        # x = lines that missed L2 (demand + HW prefetch). ls_any_fills_from_sys.local_ccx is NOT
        # used: lines the L2 prefetcher pulled from L3 are later counted as L1 fills "from L2".
        l2miss = g["l2_cache_req_stat.ic_dc_miss_in_l2_per_work"] + g["l2_pf_miss_per_work"]
        axs[2].scatter(l2miss.clip(lower=1e-6), g.ns_per_elem_median, color=COLORS[i], marker=MARKERS[i], label=c)
    axs[0].set_yscale("log"); axs[0].set_ylabel("ns per element"); axs[0].set_title("Runtime vs footprint", pad=18)
    size_axis(axs[0]); axs[0].legend(fontsize=7)
    axs[1].set_yscale("log"); axs[1].set_ylabel("events per element"); axs[1].set_title("perf counters per element (solid: first config)", pad=18)
    size_axis(axs[1]); axs[1].legend(fontsize=7)
    axs[2].set_xscale("log"); axs[2].set_yscale("log")
    axs[2].set_xlabel("L2 misses per element (demand + HW prefetch)"); axs[2].set_ylabel("ns per element"); axs[2].set_title("Runtime vs lines fetched beyond L2")
    axs[2].legend(fontsize=7)
    save(fig, a, "kernel_cache_miss")

d = load(a, "tlb", "tlb_joined.csv")
if d is not None:
    fig, axs = plt.subplots(1, 2, figsize=(11.5, 4.6))
    i = 0
    for (o, pg), g in d.groupby(["order", "pages"], sort=False):
        g = g.sort_values("span_bytes")
        errline(axs[0], g.span_bytes, g.ns_per_access_median, g.ns_per_access_q1, g.ns_per_access_q3, f"{o} page order, {pg}", i)
        axs[1].plot(g.span_bytes, g["ls_l1_d_tlb_miss.all_l2_miss_per_work"].clip(lower=1e-6), marker=MARKERS[i], color=COLORS[i],
                    label=f"{o}, {pg}: L2-dTLB miss (page walk)", ms=4)
        axs[1].plot(g.span_bytes, g["ls_l1_d_tlb_miss.all_per_work"].clip(lower=1e-6), marker=MARKERS[i], color=COLORS[i], ls=":", ms=3, alpha=0.7)
        i += 1
    axs[0].set_yscale("log"); axs[0].set_ylabel("ns per access (1 line per 4 KiB page)")
    axs[0].set_title("Latency vs address span: 4 KiB pages vs THP"); axs[0].legend(fontsize=7)
    axs[1].set_yscale("log"); axs[1].set_ylabel("dTLB misses per access (dotted: L1 dTLB miss)")
    axs[1].set_title("Hardware counters"); axs[1].legend(fontsize=7)
    for ax in axs:
        ax.set_xscale("log", base=2); ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt_size(v)))
        ax.set_xlabel("address span (log scale)")
    save(fig, a, "tlb_miss_impact")
