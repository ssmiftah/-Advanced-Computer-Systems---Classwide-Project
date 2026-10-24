"""Exp 1/5: working-set latency sweep with cache-level annotations (+ pattern/stride latency)."""
from plot_common import *

a = args()
d = load(a, "latency", "latency.csv")
if d is not None:
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for i, ((pat, pg), g) in enumerate(d.groupby(["pattern", "pages"], sort=False)):
        g = g.sort_values("size_bytes")
        errline(ax, g.size_bytes, g.ns_per_access_median, g.ns_per_access_q1, g.ns_per_access_q3,
                f"{pat}, {pg} pages", i)
    ax.set_yscale("log")
    ax.set_ylabel("load-to-use latency per dependent access (ns, log)")
    ax.set_title("Pointer-chase latency vs working set (median, IQR bars)", pad=18)
    size_axis(ax)
    ax.legend(loc="upper left")
    save(fig, a, "latency_working_set")

d = load(a, "pattern", "latency.csv")
if d is not None:
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.8), sharey=True)
    sizes = sorted(d.size_bytes.unique())
    for ax, s in zip(axs, sizes[-3:]):
        g = d[d.size_bytes == s]
        for i, (pat, gg) in enumerate(g.groupby("pattern")):
            gg = gg.sort_values("stride")
            errline(ax, gg.stride, gg.ns_per_access_median, gg.ns_per_access_q1, gg.ns_per_access_q3, pat, i)
        ax.set_xscale("log", base=2); ax.set_yscale("log")
        ax.set_title(f"buffer {fmt_size(s)}"); ax.set_xlabel("stride (bytes)")
    axs[0].set_ylabel("ns per dependent access"); axs[0].legend()
    save(fig, a, "latency_pattern_stride")
