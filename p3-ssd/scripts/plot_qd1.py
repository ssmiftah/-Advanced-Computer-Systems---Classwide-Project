#!/usr/bin/env python3
"""Exp 1: QD=1 latency table (CSV+markdown) and percentile bar plot."""
from plotlib import *

df = agg("qd1")
names = {"randread_4k": "4K rand read", "randwrite_4k": "4K rand write",
         "seqread_128k": "128K seq read", "seqwrite_128k": "128K seq write"}
rows = []
for _, r in df.iterrows():
    p = "r_" if r.rw in ("randread", "read") else "w_"
    rows.append({"workload": names.get(r.label, r.label), "reps": int(r.n_reps),
                 "IOPS": r[p + "iops_mean"], "MB/s (1e6)": r[p + "bw_MBps_mean"], "MiB/s (2^20)": r[p + "bw_MiBps_mean"],
                 "mean_us": r[p + "lat_mean_us_mean"], "mean_us_std": r[p + "lat_mean_us_std"],
                 "p50_us": r[p + "clat_p50_us_mean"], "p95_us": r[p + "clat_p95_us_mean"],
                 "p99_us": r[p + "clat_p99_us_mean"], "p99.9_us": r[p + "clat_p99.9_us_mean"],
                 "p99.99_us": r[p + "clat_p99.99_us_mean"]})
t = pd.DataFrame(rows)
table_out(t.round(2), "qd1_latency_table")
fig, ax = plt.subplots(figsize=(7, 4))
ps = ["mean_us", "p50_us", "p95_us", "p99_us", "p99.9_us"]
w = 0.8 / len(ps)
for i, p in enumerate(ps):
    ax.bar(np.arange(len(t)) + i * w, t[p], w, label=p.replace("_us", ""), color=CL[i])
ax.set_xticks(np.arange(len(t)) + 0.4 - w / 2); ax.set_xticklabels(t.workload, rotation=10)
ax.set_yscale("log"); ax.set_ylabel("latency (us, log)"); ax.set_title("QD=1 latency: mean and clat percentiles")
ax.legend(ncol=5, fontsize=8)
save(fig, "qd1_latency")
