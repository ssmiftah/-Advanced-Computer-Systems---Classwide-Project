#!/usr/bin/env python3
"""Exp 2: block-size sweep. One figure per QD: MB/s, IOPS, mean latency, p99 latency vs block size."""
from plotlib import *

df = agg("bs_sweep")
for qd, d in df.groupby("iodepth"):
    fig, axs = plt.subplots(2, 2, figsize=(10, 7), sharex=True)
    series = [(pat, op) for pat in ("random", "sequential") for op in ("read", "write")]
    for k, (pat, op) in enumerate(series):
        s = d[(d.pattern == pat) & (d.rw.str.contains(op))].sort_values("bs_bytes")
        if s.empty: continue
        p = "r_" if op == "read" else "w_"
        x = s.bs_bytes
        kw = dict(marker="o", color=CL[k], label=f"{pat} {op}", capsize=2)
        axs[0, 0].errorbar(x, s[p + "bw_MBps_mean"], yerr=err(s, p + "bw_MBps"), **kw)
        axs[0, 1].errorbar(x, s[p + "iops_mean"], yerr=err(s, p + "iops"), **kw)
        axs[1, 0].errorbar(x, s[p + "lat_mean_us_mean"], yerr=err(s, p + "lat_mean_us"), **kw)
        axs[1, 1].errorbar(x, s[p + "clat_p99_us_mean"], **kw)
    for a, t in zip(axs.flat, ["Bandwidth (MB/s, 1e6 B)", "IOPS", "Mean latency (us)", "p99 completion latency (us)"]):
        a.set_ylabel(t); a.set_xscale("log", base=2); a.set_yscale("log" if "latency" in t or t == "IOPS" else "linear")
    for a in axs[1]:
        a.set_xlabel("block size")
        a.set_xticks(sorted(d.bs_bytes.unique())); a.set_xticklabels([bs_label(b) for b in sorted(d.bs_bytes.unique())])
    axs[0, 0].legend(fontsize=8)
    fig.suptitle(f"Block-size sweep, QD={qd} (direct=1, error bars = std over repeats)")
    save(fig, f"bs_sweep_qd{qd}")
