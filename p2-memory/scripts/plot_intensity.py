"""Exp 4: throughput vs latency, knee, Little's law."""
from plot_common import *


def knee(x, y):
    """Kneedle on a convex-increasing latency(throughput) curve: point farthest below the chord."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return len(x) - 1
    xn = (x - x.min()) / np.ptp(x); yn = (y - y.min()) / np.ptp(y)
    return int(np.argmax(xn - yn))


a = args()
d = load(a, "intensity", "mlp.csv")
if d is not None:
    fig, axs = plt.subplots(1, 2, figsize=(11.5, 4.6))
    for i, (t, g) in enumerate(d.groupby("chase_threads")):
        g = g.sort_values("outstanding_cfg")
        axs[0].errorbar(g.chase_GBps_median, g.lat_ns_mean_median, yerr=[g.lat_ns_mean_median - g.lat_ns_mean_q1, g.lat_ns_mean_q3 - g.lat_ns_mean_median],
                        marker=MARKERS[i % 7], color=COLORS[i % 7], ms=4, capsize=2, label=f"{t} thread(s), K=1..{g.chains.max()} chains")
        if t == d.chase_threads.max():
            k = knee(g.chase_GBps_median, g.lat_ns_mean_median)
            kx, ky, ko = g.chase_GBps_median.iloc[k], g.lat_ns_mean_median.iloc[k], int(g.outstanding_cfg.iloc[k])
            axs[0].annotate(f"knee: {kx:.0f} GB/s, {ky:.0f} ns,\n~{ko} outstanding lines", (kx, ky), (0.35, 0.75),
                            textcoords="axes fraction", arrowprops=dict(arrowstyle="->"), fontsize=8)
    axs[0].set_xlabel("throughput (GB/s, 64 B per outstanding line)"); axs[0].set_ylabel("latency per hop (ns)")
    axs[0].set_title("Latency vs throughput (MLP sweep)"); axs[0].legend(fontsize=7)
    # Little's law with INDEPENDENT inputs: predict throughput from the configured concurrency
    # N = T x K and the zero-load latency R0 (T=1, K=1):  X = N x 64 B / R0. The measured
    # throughput departs from this line where queueing raises the latency (BW x latency =
    # N holds by construction for the chase itself, so it is not plotted as "evidence").
    r0 = d[(d.chase_threads == 1) & (d.chains == 1)].lat_ns_mean_median
    r0 = float(r0.iloc[0]) if len(r0) else float(d.lat_ns_mean_median.min())
    for i, (t, g) in enumerate(d.groupby("chase_threads")):
        g = g.sort_values("outstanding_cfg")
        axs[1].plot(g.outstanding_cfg, g.chase_GBps_median, marker=MARKERS[i % 7], color=COLORS[i % 7], ms=4, label=f"measured, {t} thread(s)")
    n = np.linspace(1, d.outstanding_cfg.max(), 200)
    xmax = d.chase_GBps_median.max()
    axs[1].plot(n, n * 64 / r0, "k--", lw=0.8, label=f"Little's law, no queueing: N x 64 B / R0 (R0 = {r0:.0f} ns)")
    axs[1].set_ylim(0, xmax * 1.25)
    axs[1].text(0.02, 0.97, f"concurrency needed for {xmax:.0f} GB/s at R0: {xmax * r0 / 64:.0f} lines", transform=axs[1].transAxes, va="top", fontsize=8)
    axs[1].set_xlabel("configured outstanding requests N (threads x chains)"); axs[1].set_ylabel("throughput (GB/s)")
    axs[1].legend(fontsize=7, loc="lower right")
    axs[1].set_title("Little's law: predicted (idle latency) vs measured throughput", fontsize=9)
    save(fig, a, "intensity_mlp")

d = load(a, "intensity", "loaded_latency.csv")
if d is not None:
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    g = d.sort_values("total_GBps_median")
    ax.errorbar(g.total_GBps_median, g.lat_ns_mean_median, yerr=[g.lat_ns_mean_median - g.lat_ns_mean_q1, g.lat_ns_mean_q3 - g.lat_ns_mean_median],
                marker="o", capsize=2, color=COLORS[0])
    k = knee(g.total_GBps_median, g.lat_ns_mean_median)
    ax.annotate(f"knee ~{g.total_GBps_median.iloc[k]:.0f} GB/s", (g.total_GBps_median.iloc[k], g.lat_ns_mean_median.iloc[k]),
                (0.3, 0.8), textcoords="axes fraction", arrowprops=dict(arrowstyle="->"))
    # Little's law from two independent measurements (bandwidth of the streamers + probe
    # latency, assuming the streamers' misses see the probe's latency): lines in flight in the
    # memory system N = X x R / 64 B. Nothing in the setup fixes N (it is set by the cores'
    # miss buffers + prefetchers), so this is an inference, not an identity.
    ax2 = ax.twinx(); ax2.grid(False)
    inflight = g.total_GBps_median * g.lat_ns_mean_median / 64
    ax2.plot(g.total_GBps_median, inflight, "s:", color=COLORS[1], ms=3, label="inferred lines in flight = X x R / 64 B")
    ax2.set_ylabel("Little's law: lines in flight", color=COLORS[1]); ax2.legend(loc="upper left", fontsize=7)
    j = int(np.argmax(inflight.values))
    ax2.annotate(f"{inflight.iloc[j]:.0f} lines at {g.total_GBps_median.iloc[j]:.0f} GB/s", (g.total_GBps_median.iloc[j], inflight.iloc[j]),
                 (0.05, 0.6), textcoords="axes fraction", fontsize=7, arrowprops=dict(arrowstyle="->", color=COLORS[1]))
    ax.set_xlabel("total bandwidth: probe + background (GB/s)"); ax.set_ylabel("probe latency (ns)")
    ax.set_title("MLC-style loaded latency (background read streams, varying delay)")
    save(fig, a, "intensity_loaded_latency")
