#!/usr/bin/env python3
"""Exp 7: misleading setups: buffered vs direct, and iodepth with a sync engine (effective QD 1)."""
from plotlib import *

df = agg("misleading")
fig, axs = plt.subplots(1, 3, figsize=(14, 4.2))
a = axs[0]; w = 0.38
cache = df[df.demo.isin(["cache", "cachew"])]
names = [("randread_4k", "4K rand read"), ("seqread_128k", "128K seq read"), ("randwrite_4k", "4K rand write")]
tab = []
for i, (pre, nm) in enumerate(names):
    for j, d in enumerate((1, 0)):
        r = cache[cache.label == f"{pre}_direct{d}"]
        if r.empty: continue
        r = r.iloc[0]; p = "w_" if "write" in pre else "r_"
        a.bar(i + (j - .5) * w, r[p + "bw_MBps_mean"], w, color=[C["blue"], C["red"]][j], label=["direct=1", "buffered (direct=0)"][j] if i == 0 else None)
        tab.append({"workload": nm, "direct": d, "MB/s": r[p + "bw_MBps_mean"], "IOPS": r[p + "iops_mean"], "mean_us": r[p + "lat_mean_us_mean"]})
a.set_xticks(range(len(names))); a.set_xticklabels([n for _, n in names]); a.set_yscale("log"); a.set_ylabel("bandwidth (MB/s, log)")
a.legend(fontsize=8); a.set_title("Page cache inflates buffered I/O (1 GiB span)")
qd = df[df.demo == "qd"]
order = ["randread_4k_uring_qd1", "randread_4k_psync_qd32", "randread_4k_uring_qd32"]
nm = ["io_uring\niodepth=1", "psync\niodepth=32\n(=QD1!)", "io_uring\niodepth=32"]
qd = qd.set_index("label").reindex([o for o in order if o in set(qd.label)])
axs[1].bar(range(len(qd)), qd.r_iops_mean / 1e3, yerr=qd.r_iops_std / 1e3, color=[C["blue"], C["red"], C["green"]][:len(qd)], capsize=3)
axs[1].set_xticks(range(len(qd))); axs[1].set_xticklabels([nm[order.index(l)] for l in qd.index], fontsize=8)
axs[1].set_ylabel("4K random read kIOPS"); axs[1].set_title("Requested vs effective queue depth")
axs[2].bar(range(len(qd)), qd.outstanding_eff_mean, color=[C["blue"], C["red"], C["green"]][:len(qd)])
axs[2].set_xticks(range(len(qd))); axs[2].set_xticklabels([nm[order.index(l)] for l in qd.index], fontsize=8)
axs[2].set_ylabel("effective QD = IOPS x mean latency"); axs[2].set_title("Little's Law: what the SSD actually saw")
save(fig, "misleading_setup")
table_out(pd.DataFrame(tab).round(2), "misleading_cache_table")
