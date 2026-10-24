#!/usr/bin/env python3
"""Experiment 7: roofline (single thread, float32).

Ceilings
  compute : empirical FMA peak from bin/peakflops (processed/peakflops_summary.csv) for zmm/ymm/xmm,
            and the theoretical zmm peak = 64 FLOP/cycle x measured core clock (dashed).
  memory  : single-thread read bandwidth from bin/membw (L1/L2/L3/DRAM levels), or an external number
            via --bw-gibs (e.g. the multi-thread DRAM bandwidth measured in Project 2).
Points : each kernel's measured GFLOP/s at its arithmetic intensity AI = FLOP / nominal bytes
         (saxpy 2/12, dot 2/8, mul 1/12, stencil 5/8 FLOP/byte for f32), from the locality sweep:
         large markers = DRAM-sized footprint (largest ws), small faint = smaller footprints.
Units: AI in FLOP/byte, bandwidth converted GiB/s -> GB/s (x1.0737) so slope*AI is GFLOP/s.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from plot_common import *

ap = args(__doc__)
ap.add_argument("--bw-gibs", type=float, help="DRAM bandwidth ceiling in GiB/s (default: measured single-thread read)")
ap.add_argument("--bw-label", default=None)
ap.add_argument("--peak-gflops", type=float, help="override compute peak (default: measured fp32 zmm FMA)")
ap.add_argument("--builds", default="scalar,sse,avx2,znver5,znver5_fm")
a = ap.parse_args()

G = 1.073741824
pk = load(a.proc, "peakflops_summary.csv").set_index("kind")
rd = load(a.proc, "bandwidth_read_summary.csv")
ghz = pk.loc["fp32_zmm", "ghz_med"]
peaks = {"fp32 zmm FMA (measured)": a.peak_gflops or pk.loc["fp32_zmm", "gflops_med"],
         "fp32 ymm FMA (measured)": pk.loc["fp32_ymm", "gflops_med"],
         "fp32 xmm FMA (measured)": pk.loc["fp32_xmm", "gflops_med"]}
theo = 64 * ghz
mem = {}
sizes = sorted(set(rd.size_kib))
for lab, kib in (("L1", 16), ("L2", 512), ("L3", 16384), ("DRAM", max(sizes))):
    r = rd[rd.size_kib == min(sizes, key=lambda s: abs(s - kib))]
    if len(r):
        mem[f"{lab} read, 1 thread ({int(r.size_kib.iloc[0])} KiB)"] = r.gibs_med.iloc[0] * G
if a.bw_gibs:
    mem[a.bw_label or "DRAM (external)"] = a.bw_gibs * G

d = load(a.proc, "locality_summary.csv")
d = d[(d.type == "f32") & (d.variant == "unit") & d.build.isin(a.builds.split(","))].copy()
d["ai"] = d.flops / d.bytes_nominal

fig, ax = plt.subplots(figsize=(8.5, 6))
x = np.logspace(-3, 1.5, 200)
ymax = max(peaks.values())
for (lab, bw), ls in zip(mem.items(), ["-", "-", "-", "-", "-."]):
    ax.plot(x, np.minimum(bw * x, ymax), ls=ls, lw=1.2, color="0.25" if "DRAM" in lab else "0.65", label=f"{lab}: {bw:.0f} GB/s")
for lab, p in peaks.items():
    ax.axhline(p, color="#b22", lw=1, ls="-" if "zmm" in lab else "--", alpha=0.8 if "zmm" in lab else 0.5)
    ax.text(x[-1], p, f" {lab}: {p:.0f}", ha="right", va="bottom", fontsize=7, color="#b22")
ax.axhline(theo, color="#b22", lw=0.8, ls=":")
ax.text(x[0], theo, f" theoretical 64 FLOP/cyc x {ghz:.2f} GHz = {theo:.0f}", va="bottom", fontsize=7, color="#b22")
for b, g in d.groupby("build"):
    st = style(b)
    big = g[g.ws_bytes == g.ws_bytes.max()]
    ax.scatter(g.ai, g.gflops_med, color=st["color"], marker=st["marker"], s=10, alpha=0.3)
    ax.scatter(big.ai, big.gflops_med, color=st["color"], marker=st["marker"], s=70, edgecolor="k", label=st["label"] + " (DRAM-size)")
    for _, r in big.iterrows():
        ax.annotate(r.kernel, (r.ai, r.gflops_med), fontsize=6, xytext=(4, 4), textcoords="offset points")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("arithmetic intensity (FLOP / byte of algorithmic traffic)")
ax.set_ylabel("performance (GFLOP/s, single thread)")
ax.set_title("Roofline, float32, one Zen 5 core (small markers: smaller footprints)")
ax.set_ylim(1, ymax * 3)
ax.set_xlim(0.02, 30)
ax.legend(fontsize=6, loc="lower right")
save(fig, a.fig, "roofline")
