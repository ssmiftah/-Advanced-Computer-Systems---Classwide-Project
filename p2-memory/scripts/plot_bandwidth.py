"""Exp 2 (pattern/granularity bandwidth) and Exp 3 (read/write mix)."""
from plot_common import *

a = args()
d = load(a, "pattern", "bandwidth.csv")
if d is not None:
    threads = sorted(d.threads.unique()); sizes = sorted(d.size_per_thread.unique())
    fig, axs = plt.subplots(len(threads), len(sizes), figsize=(5.2 * len(sizes), 3.6 * len(threads)),
                            squeeze=False)
    for r, t in enumerate(threads):
        for c, s in enumerate(sizes):
            ax = axs[r][c]
            g = d[(d.threads == t) & (d.size_per_thread == s)]
            i = 0
            for (pat, acc), gg in g.groupby(["pattern", "access"]):
                gg = gg.sort_values("stride")
                errline(ax, gg.stride, gg.useful_GBps_median, gg.useful_GBps_q1, gg.useful_GBps_q3,
                        f"{pat}, {acc} B/access: useful", i)
                if acc == 8:
                    ax.plot(gg.stride, gg.line_GBps_median, ls=":", color=COLORS[i], label=f"{pat}, 8 B: cache-line traffic")
                i += 1
            ax.set_xscale("log", base=2); ax.set_yscale("log")
            ax.set_title(f"{t} thread(s), {fmt_size(s)}/thread", fontsize=9)
            ax.set_xlabel("stride (bytes)"); ax.set_ylabel("GB/s (1e9 B/s)")
    axs[0][0].legend(fontsize=7)
    fig.suptitle("Read bandwidth vs pattern / stride / access size")
    fig.tight_layout()
    save(fig, a, "bandwidth_pattern_stride")

d = load(a, "rwmix", "bandwidth.csv")
if d is not None:
    d = d.assign(variant=np.where(d.nt == 1, "NT stores", "normal stores"))
    threads = sorted(d.threads.unique())
    fig, axs = plt.subplots(1, len(threads), figsize=(5.4 * len(threads), 4), squeeze=False)
    mixes = ["1:0", "7:3", "1:1", "0:1"]; names = {"1:0": "100% R", "7:3": "70/30", "1:1": "50/50", "0:1": "100% W"}
    for ax, t in zip(axs[0], threads):
        g = d[d.threads == t]; w = 0.2
        for j, v in enumerate(["normal stores", "NT stores"]):
            gv = g[g.variant == v].set_index("rw").reindex(mixes)
            x = np.arange(len(mixes)) + (j - 0.5) * w * 2
            ax.bar(x - w / 2, gv.useful_GBps_median, w, color=COLORS[j], label=f"{v}: program bytes")
            ax.bar(x + w / 2, gv.est_mem_GBps_median, w, color=COLORS[j], alpha=0.45,
                   label=f"{v}: est. DRAM traffic")
        ax.set_xticks(range(len(mixes)), [names[m] for m in mixes]); ax.set_ylabel("GB/s")
        ax.set_title(f"{t} thread(s), sequential, DRAM-sized")
    axs[0][0].legend(fontsize=7)
    save(fig, a, "bandwidth_rwmix")

d = load(a, "rwmix", "loaded_latency.csv")
if d is not None:
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    idle = d[d.bg_threads == 0]
    if len(idle):
        ax.axhline(idle.lat_ns_mean_median.iloc[0], color="gray", ls="--", label="idle latency")
    for i, (m, g) in enumerate(d[d.bg_threads > 0].groupby("bg_rw", sort=False)):
        g = g.sort_values("total_GBps_median")
        ax.plot(g.total_GBps_median, g.lat_ns_mean_median, marker=MARKERS[i], color=COLORS[i], label=f"bg mix {m} (R:W)")
    ax.set_xlabel("total memory traffic seen by program (GB/s)"); ax.set_ylabel("probe latency (ns)")
    ax.set_title("Loaded latency under different read/write mixes"); ax.legend()
    save(fig, a, "loaded_latency_rwmix")
