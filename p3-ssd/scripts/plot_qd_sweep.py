#!/usr/bin/env python3
"""Exp 4: throughput-vs-latency curve, knee detection, Little's Law table.

Knee heuristic (documented, tunable via env KNEE_GAIN=0.10, KNEE_LAT=0.25):
  Sort points of a series (iodepth or numjobs) by outstanding IOs N. Find the first step i where
  throughput gain over the previous point is < KNEE_GAIN (10%) AND mean-latency growth is > KNEE_LAT (25%).
  The knee is the point BEFORE that step (the last N still buying real throughput).
  If no step qualifies, the knee is the smallest N reaching >= 95% of peak IOPS.
Writes data/processed/knee.txt: '<series> <op> <knee_N>' (run_tail.sh reads the iodepth/randread line).
"""
import json
from plotlib import *

GAIN, LAT = float(os.environ.get("KNEE_GAIN", 0.10)), float(os.environ.get("KNEE_LAT", 0.25))


def knee_index(iops, lat):
    for i in range(1, len(iops)):
        if (iops[i] / iops[i - 1] - 1) < GAIN and (lat[i] / lat[i - 1] - 1) > LAT:
            return i - 1
    return int(np.argmax(np.array(iops) >= 0.95 * max(iops)))


df = agg("qd_sweep")
df["op"] = df.rw
knees, little = [], []
for series in ("iodepth", "numjobs"):
    s_all = df[df.series == series]
    if s_all.empty: continue
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.3))
    for k, (op, s) in enumerate(s_all.groupby("op")):
        s = s.sort_values("outstanding_cfg")
        p = "r_" if "read" in op else "w_"
        iops, lat = s.tot_iops_mean.values, s.tot_lat_mean_us_mean.values
        n = s.outstanding_cfg.values
        ki = knee_index(iops, lat); knees.append((series, op, int(n[ki])))
        axs[0].errorbar(iops / 1e3, lat, xerr=s.tot_iops_std / 1e3, yerr=s.tot_lat_mean_us_std, marker="o", color=CL[k], capsize=2, label=op)
        for xi, yi, ni in zip(iops / 1e3, lat, n):
            axs[0].annotate(str(ni), (xi, yi), textcoords="offset points", xytext=(4, 4), fontsize=7)
        axs[0].plot(iops[ki] / 1e3, lat[ki], marker="*", ms=16, mfc="none", mec="k", ls="none")
        axs[0].annotate(f"knee N={n[ki]}", (iops[ki] / 1e3, lat[ki]), textcoords="offset points", xytext=(-55, -18), fontsize=8,
                        arrowprops=dict(arrowstyle="->"))
        axs[1].errorbar(n, s.outstanding_eff_mean, yerr=s.outstanding_eff_std, marker="o", color=CL[k], capsize=2, label=op)
        for _, r in s.iterrows():
            little.append({"series": series, "op": op, "configured_N": int(r.outstanding_cfg),
                           "IOPS": r.tot_iops_mean, "mean_lat_us": r.tot_lat_mean_us_mean,
                           "effective_N = IOPS x lat": r.outstanding_eff_mean,
                           "eff/cfg": r.outstanding_eff_mean / r.outstanding_cfg,
                           "p99_us": r[p + "clat_p99_us_mean"]})
    axs[0].set_xlabel("throughput (kIOPS)"); axs[0].set_ylabel("mean latency (us, log)"); axs[0].set_yscale("log")
    axs[0].set_title(f"Throughput vs latency ({series} sweep; labels = outstanding IOs)"); axs[0].legend()
    mx = s_all.outstanding_cfg.max()
    axs[1].plot([1, mx], [1, mx], "k:", label="ideal (eff = cfg)")
    axs[1].set_xscale("log", base=2); axs[1].set_yscale("log", base=2)
    axs[1].set_xlabel("configured outstanding IOs (iodepth x numjobs)"); axs[1].set_ylabel("effective = IOPS x mean latency")
    axs[1].set_title("Little's Law check"); axs[1].legend()
    save(fig, f"qd_sweep_{series}")
t = pd.DataFrame(little)
table_out(t.round(3), "littles_law_table")
with open(os.path.join(PROC, "knee.txt"), "w") as f:
    for k in knees: f.write("%s %s %d\n" % k)
print("knees:", knees)
