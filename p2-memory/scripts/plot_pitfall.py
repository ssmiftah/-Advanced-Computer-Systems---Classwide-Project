"""Exp 8: pitfall side-by-side figures."""
from plot_common import *

a = args()
fig, axs = plt.subplots(1, 3, figsize=(14, 4.2))
d = load(a, "pitfall", "p1_bandwidth.csv"); l = load(a, "pitfall", "p1_latency.csv")
if d is not None:
    d = d.assign(lab=d.threads.astype(str) + "T x " + d.size_per_thread.map(fmt_size))
    ax = axs[0]; ax.bar(range(len(d)), d.useful_GBps_median, color=[COLORS[1] if t * sz < 64 * MIB else COLORS[0] for t, sz in zip(d.threads, d.size_per_thread)])
    ax.set_xticks(range(len(d)), d.lab, rotation=40, ha="right", fontsize=8)
    ax.set_ylabel("read bandwidth (GB/s)"); ax.set_title("P1: 'DRAM' test sized to fit in L3 (orange: total < 64 MiB)")
if l is not None:
    ax = axs[0].twinx(); ax.grid(False)
    ax.plot(range(len(l)), l.ns_per_access_median, "k^", label="latency (ns), 1T chase"); ax.set_ylabel("ns"); ax.legend(loc="upper center", fontsize=7)
d = load(a, "pitfall", "p2_nowarm.csv")
if d is not None:
    d = d.assign(lab=d.pages + np.where(d.prefault == 0, ", untouched\n(zero page)", ", pre-faulted"))
    axs[1].bar(range(len(d)), d.useful_GBps_median, color=COLORS[:len(d)])
    axs[1].set_xticks(range(len(d)), d.lab, fontsize=8); axs[1].set_ylabel("read bandwidth (GB/s)")
    axs[1].set_title("P2: reading memory that was never written")
d = load(a, "pitfall", "p3_pinning.csv")
if d is not None:
    sib = [abs(int(c.split("+")[1]) - int(c.split("+")[0])) == 16 for c in d.cpus.astype(str)]
    d = d.assign(lab=["cpus " + c.replace("+", ",") + ("\n(SMT siblings)" if s else "\n(2 cores)") + "\n2 x " + fmt_size(z)
                      for c, s, z in zip(d.cpus.astype(str), sib, d.size_per_thread)])
    axs[2].bar(range(len(d)), d.useful_GBps_median, color=[COLORS[1] if s else COLORS[0] for s in sib])
    axs[2].set_xticks(range(len(d)), d.lab, fontsize=7); axs[2].set_ylabel("aggregate read GB/s (2 threads)")
    axs[2].set_title("P3: 2 threads on SMT siblings (orange) vs 2 cores (blue)")
fig.tight_layout()
save(fig, a, "pitfalls")
