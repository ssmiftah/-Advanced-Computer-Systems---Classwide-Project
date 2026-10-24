#!/usr/bin/env python3
"""Exp 6a: effect of the accessed LBA range (span) on 4K random IO (QD32)."""
from plotlib import *

df = agg("workingset")
df["span_gib"] = df.span_bytes / 2**30
fig, axs = plt.subplots(1, 2, figsize=(10, 4))
for k, (op, s) in enumerate(df.groupby("rw")):
    s = s.sort_values("span_gib"); p = "r_" if "read" in op else "w_"
    axs[0].errorbar(s.span_gib, s[p + "iops_mean"], yerr=s[p + "iops_std"], marker="o", color=CL[k], capsize=2, label=op)
    axs[1].errorbar(s.span_gib, s[p + "clat_p99_us_mean"], marker="o", color=CL[k], label=op + " p99")
    axs[1].errorbar(s.span_gib, s[p + "lat_mean_us_mean"], marker="s", ls="--", color=CL[k], label=op + " mean")
for a, t in zip(axs, ["IOPS", "latency (us)"]):
    a.set_xscale("log", base=2); a.set_xlabel("random-IO span within the test file (GiB)"); a.set_ylabel(t); a.legend(fontsize=8)
axs[1].set_yscale("log")
fig.suptitle("Working-set (LBA range) sweep: 4K random, QD32, direct=1")
save(fig, "workingset")
