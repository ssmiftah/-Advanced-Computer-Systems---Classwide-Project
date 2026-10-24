#!/usr/bin/env python3
"""Experiment 4 figure: unit stride vs stride 2/4/8 vs gather (perm / blocked) per size."""
import matplotlib.pyplot as plt
import numpy as np
from plot_common import *

ap = args(__doc__)
a = ap.parse_args()
d = load(a.proc, "stride_gather_summary.csv")


def pattern(r):
    if r.variant == "unit": return "unit\n(plain)"
    if r.variant == "stride": return f"stride\n{int(r.stride)}"
    return f"gather\n{r.gather}"


d["pat"] = d.apply(pattern, axis=1)
order = ["unit\n(plain)"] + [f"stride\n{s}" for s in (1, 2, 4, 8)] + ["gather\nperm", "gather\nblock"]
order = [o for o in order if o in set(d.pat)]
kernels = [k for k in ("saxpy", "dot") if k in set(d.kernel)]
ns = sorted(set(d.n))
for ycol, lo, hi, yl, name in [("cyc_per_elem_med", "cyc_per_elem_q1", "cyc_per_elem_q3", "core cycles / element", "stride_cycles"),
                               ("gibs_med", "gibs_q1", "gibs_q3", "useful bandwidth (GiB/s)", "stride_gibs")]:
    fig, axs = plt.subplots(len(kernels), len(ns), figsize=(2.9 * len(ns), 3.2 * len(kernels)), squeeze=False, sharey="row")
    for i, k in enumerate(kernels):
        for j, n in enumerate(ns):
            ax = axs[i][j]
            g = d[(d.kernel == k) & (d.n == n) & (d.type == "f32")]
            for b, gb in g.groupby("build"):
                gb = gb.set_index("pat").reindex(order)
                x = np.arange(len(order))
                st = style(b)
                ax.plot(x, gb[ycol], **st)
                ax.fill_between(x, gb[lo], gb[hi], color=st["color"], alpha=0.2, lw=0)
            ax.set_xticks(range(len(order)))
            ax.set_xticklabels(order, fontsize=6)
            ax.set_yscale("log")
            ax.set_title(f"{k}, n={n} (unit x+y = {human(2 * 4 * n)})", fontsize=8)
            if j == 0: ax.set_ylabel(yl)
    axs[0][0].legend(fontsize=6)
    fig.suptitle("Stride and gather (float32): x read at x[i*s] or x[idx[i]]\nfixed n (median, IQR band)", fontsize=10)
    save(fig, a.fig, name)
