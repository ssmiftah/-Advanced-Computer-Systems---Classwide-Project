#!/usr/bin/env python3
"""Experiment 5 figure: f32 vs f64 vs i32 (equal byte footprint) per kernel, scalar vs best vector build."""
import matplotlib.pyplot as plt
import numpy as np
from plot_common import *

ap = args(__doc__)
a = ap.parse_args()
d = load(a.proc, "dtype_speedup.csv")
d = d[d.variant == "unit"]
kernels = [k for k in KERNEL_TITLE if k in set(d.kernel)]
wss = sorted(set(d.ws_bytes))
types = ["f32", "f64", "i32"]
cols = {"f32": "#0072B2", "f64": "#D55E00", "i32": "#009E73"}


def pick(g, k, t, vec):
    # vector build: znver5 (dot FP needs the assoc-math build to actually vectorize the reduction)
    b = "scalar" if not vec else ("znver5_fm" if (k == "dot" and t != "i32") else "znver5")
    r = g[(g.kernel == k) & (g.type == t) & (g.build == b)]
    return r.iloc[0] if len(r) else None


for metric, yl, name in [("gflops", "throughput (GFLOP/s or Gop/s for i32)", "dtype_gflops"),
                         ("speedup", "speedup over scalar (x)", "dtype_speedup")]:
    fig, axs = plt.subplots(1, len(wss), figsize=(3.6 * len(wss), 3.8), squeeze=False, sharey=False)
    for ax, w in zip(axs[0], wss):
        g = d[d.ws_bytes == w]
        x = np.arange(len(kernels))
        for ti, t in enumerate(types):
            v = [pick(g, k, t, True) for k in kernels]
            if metric == "gflops":
                y = [r.gflops_med if r is not None else np.nan for r in v]
                lo = [r.gflops_med - r.gflops_q1 if r is not None else 0 for r in v]
                hi = [r.gflops_q3 - r.gflops_med if r is not None else 0 for r in v]
            else:
                y = [r.speedup if r is not None else np.nan for r in v]
                lo = [r.speedup - r.speedup_lo if r is not None else 0 for r in v]
                hi = [r.speedup_hi - r.speedup if r is not None else 0 for r in v]
            ax.bar(x + (ti - 1) * 0.27, y, 0.27, yerr=[lo, hi], color=cols[t], label=t, capsize=2)
            if metric == "gflops":  # scalar reference as black tick
                sc = [pick(g, k, t, False) for k in kernels]
                ax.scatter(x + (ti - 1) * 0.27, [r.gflops_med if r is not None else np.nan for r in sc], marker="_", color="k", s=60, zorder=5,
                           label="scalar" if ti == 0 else None)
        ax.set_xticks(x)
        ax.set_xticklabels(kernels, fontsize=8)
        ax.set_yscale("log")
        ax.set_title(f"footprint {human(w)}", fontsize=9)
        ax.set_ylabel(yl)
    axs[0][0].legend(fontsize=7)
    fig.suptitle("Data type comparison, best vector build (znver5; dot FP: znver5+assoc-math) vs scalar")
    save(fig, a.fig, name)
