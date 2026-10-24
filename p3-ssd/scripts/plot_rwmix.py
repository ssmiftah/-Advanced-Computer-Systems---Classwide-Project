#!/usr/bin/env python3
"""Exp 3: R/W mix. Stacked read/write IOPS & MB/s bars; read/write p99 latency."""
from plotlib import *

df = agg("rwmix").sort_values("rwmix", ascending=False)
x = np.arange(len(df)); lab = [f"{m}% R" for m in df.rwmix]
fig, axs = plt.subplots(1, 3, figsize=(13, 4))
for a, met, t in zip(axs[:2], ["iops", "bw_MBps"], ["IOPS", "Bandwidth (MB/s, 1e6 B)"]):
    a.bar(x, df["r_" + met + "_mean"], color=C["blue"], label="read")
    a.bar(x, df["w_" + met + "_mean"], bottom=df["r_" + met + "_mean"], color=C["orange"], label="write")
    a.errorbar(x, df["tot_" + met + "_mean"], yerr=df["tot_" + met + "_std"], fmt="none", ecolor="k", capsize=3)
    a.set_xticks(x); a.set_xticklabels(lab); a.set_ylabel(t); a.set_title(t + " (stacked read+write)")
axs[0].legend()
a = axs[2]
for k, (p, n) in enumerate([("r_", "read"), ("w_", "write")]):
    for j, q in enumerate(["clat_p50_us", "clat_p99_us", "clat_p99.9_us"]):
        a.plot(x, df[p + q + "_mean"], marker="os^"[j], ls="-" if p == "r_" else "--", color=CL[k], label=f"{n} {q.split('_')[1]}")
a.set_yscale("log"); a.set_xticks(x); a.set_xticklabels(lab); a.set_ylabel("completion latency (us)"); a.legend(fontsize=7, ncol=2)
a.set_title("Latency percentiles per direction")
fig.suptitle(f"R/W mix sweep (bs={df.bs.iloc[0]}, random, QD={df.iodepth.iloc[0]})")
save(fig, "rwmix")
