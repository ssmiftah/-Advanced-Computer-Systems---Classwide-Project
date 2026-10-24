#!/usr/bin/env python3
"""Exp 5: tail latency at mid-QD and near-knee QD: percentile bars + CDF from json+ clat histogram bins."""
import glob, json, collections
from plotlib import *

df = agg("tail")
tab = []
fig, axs = plt.subplots(1, 2, figsize=(12, 4.3))
ps = ["p50", "p95", "p99", "p99.9", "p99.99"]
labels = list(df.label)
w = 0.8 / max(len(labels), 1)
for i, (_, r) in enumerate(df.iterrows()):
    p = "r_"
    vals = [r[p + f"clat_{q}_us_mean"] for q in ps]
    axs[0].bar(np.arange(len(ps)) + i * w, vals, w, color=CL[i % len(CL)], label=r.label)
    tab.append({"label": r.label, "QD": int(r.iodepth), "read IOPS": r.r_iops_mean, "mean_us": r.r_lat_mean_us_mean,
                **{q + "_us": v for q, v in zip(ps, vals)}})
    # CDF: merge histogram bins over reps
    bins = collections.Counter()
    for jp in glob.glob(os.path.join(RAW, "tail", r.label + "_rep*.json")):
        txt = open(jp).read(); d = json.loads(txt[txt.index("{"):])
        c = d["jobs"][0]["read"]["clat_ns"]
        for k, v in c.get("bins", {}).items():
            if int(k) >= c["percentile"]["1.000000"] * 0.5: bins[int(k)] += v
    if bins:
        x = np.array(sorted(bins)); cnt = np.array([bins[k] for k in x]); cdf = np.cumsum(cnt) / cnt.sum()
        axs[1].plot(x / 1e3, 1 - cdf + 1e-9, color=CL[i % len(CL)], label=r.label)
axs[0].set_xticks(np.arange(len(ps)) + 0.4 - w / 2); axs[0].set_xticklabels(ps)
axs[0].set_yscale("log"); axs[0].set_ylabel("read completion latency (us)"); axs[0].legend(fontsize=7); axs[0].set_title("Latency percentiles")
axs[1].set_xscale("log"); axs[1].set_yscale("log"); axs[1].set_xlabel("read completion latency (us)")
axs[1].set_ylabel("P(latency > x)  (complementary CDF)"); axs[1].set_ylim(1e-6, 1.05); axs[1].legend(fontsize=7)
axs[1].set_title("Tail (CCDF) from fio json+ histogram")
save(fig, "tail_latency")
table_out(pd.DataFrame(tab).round(2), "tail_latency_table")
