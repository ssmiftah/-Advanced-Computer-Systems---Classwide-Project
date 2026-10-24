#!/usr/bin/env python3
"""Exp 6b: sustained sequential write: per-second bandwidth (fio write_bw_log) + NVMe temperature vs time.
Annotates the first time bandwidth drops below DROP (70%) of the median of the first SUST_BASE_S (3) s (SLC-cache-exhaustion
or throttling candidate) -- only if it happens; otherwise states that no drop was observed."""
import glob
from plotlib import *

DROP = float(os.environ.get("SUST_DROP", 0.7))
B0 = float(os.environ.get("SUST_BASE_S", 3))  # at ~5 GB/s, 10 s would already be ~50 GB: keep the baseline window short
d = os.path.join(RAW, "sustained")
logs = sorted(glob.glob(os.path.join(d, "*_bw*.log")))
if not logs: raise SystemExit("no bandwidth logs in " + d)
temp = pd.read_csv(os.path.join(d, "temp.csv"))
fig, ax = plt.subplots(figsize=(9, 4.3)); ax2 = ax.twinx(); ax2.grid(False); ax2.spines["right"].set_visible(True)
for i, lg in enumerate(logs):
    rep = lg.split("_rep")[-1].split("_")[0]
    pr = open(lg.split("_bw")[0].rsplit("_rep", 1)[0] + "_rep" + rep + ".params")
    start = float([l.split("=")[1] for l in pr if l.startswith("start_epoch")][0])
    a = np.loadtxt(lg, delimiter=",", usecols=(0, 1), ndmin=2).reshape(-1, 2)
    if len(a) == 0:
        print(f"{lg}: empty bandwidth log (run shorter than log_avg_msec=1 s?) -- skipped"); continue
    t, bw = a[:, 0] / 1000.0, a[:, 1] * 1024 / 1e6   # fio bw log is KiB/s -> MB/s
    ax.plot(t, bw, color=CL[i % len(CL)], lw=1, label=f"write MB/s (rep {rep})")
    base = np.median(bw[t <= B0]) if (t <= B0).any() else bw[0]
    low = np.where(bw < DROP * base)[0]
    low = low[t[low] > B0] if len(low) else low
    if len(low):
        ax.axvline(t[low[0]], color="k", ls=":"); ax.annotate(f"bw < {int(DROP*100)}% of initial\n at t={t[low[0]]:.0f}s\n(~{bw[:low[0]].sum()/1e3*1e9/2**30:.0f} GiB written)", (t[low[0]], base * 0.5), fontsize=8)
        print(f"rep {rep}: bandwidth fell below {DROP:.0%} of initial ({base:.0f} MB/s) at t={t[low[0]]:.0f}s; written so far ~{bw[:low[0]].sum()/1000:.0f} GB")
    else:
        print(f"rep {rep}: no drop below {DROP:.0%} of initial ({base:.0f} MB/s) observed")
ax2.plot(temp.epoch - start, temp.temp_c, color=C["red"], lw=1, label="NVMe temp")
ax2.set_xlim(0, None); ax.set_xlim(0, None)
ax.set_xlabel("time (s)"); ax.set_ylabel("write bandwidth (MB/s, 1e6 B)"); ax2.set_ylabel("temperature (C)", color=C["red"])
ax.set_ylim(0, None)
ax.legend(loc="lower left", fontsize=8); ax.set_title("Sustained sequential write: bandwidth and temperature")
save(fig, "sustained_write")
