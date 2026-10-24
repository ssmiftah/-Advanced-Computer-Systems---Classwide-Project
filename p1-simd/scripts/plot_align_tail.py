#!/usr/bin/env python3
"""Experiment 3 figures: alignment offset study and tail (n mod vector width) study."""
import matplotlib.pyplot as plt
from plot_common import *

ap = args(__doc__)
a = ap.parse_args()
d = load(a.proc, "align_tail_summary.csv")
for t in sorted(set(d.type)):
    dt = d[d.type == t]
    # ---- alignment: variants with fixed ws (rows: kernel, cols: footprint), x = byte offset
    al = dt[dt.n >= 512].copy()  # tail runs use small / odd n; alignment runs use ws-derived n (mult. of 64)
    al = al[al.n % 64 == 0]
    multi = al.groupby('ws_bytes').offx.nunique()  # alignment sweeps = footprints measured at >1 offset
    al = al[al.ws_bytes.isin(multi[multi > 1].index)]
    kernels = [k for k in KERNEL_TITLE if k in set(al.kernel)]
    wss = sorted(set(al.ws_bytes))
    if kernels and wss:
        fig, axs = plt.subplots(len(kernels), len(wss), figsize=(4 * len(wss), 2.8 * len(kernels)), squeeze=False)
        for i, k in enumerate(kernels):
            for j, w in enumerate(wss):
                ax = axs[i][j]
                g = al[(al.kernel == k) & (al.ws_bytes == w)]
                for b, gb in g.groupby("build"):
                    both = gb[(gb.offx == gb.offy)].sort_values("offx")
                    xo = gb[(gb.offy == 0)].sort_values("offx")
                    st = style(b)
                    lab = st.pop("label")
                    ax.errorbar(both.offx, both.cyc_per_elem_med, yerr=[both.cyc_per_elem_med - both.cyc_per_elem_q1, both.cyc_per_elem_q3 - both.cyc_per_elem_med],
                                label=lab + " (x,y shifted)", capsize=2, **{k2: v for k2, v in st.items()})
                    if len(xo) > 1:
                        ax.plot(xo.offx, xo.cyc_per_elem_med, ls="--", alpha=0.6, color=st["color"], marker=st["marker"], ms=3, lw=1)
                ax.set_yscale("log")
                ax.set_title(f"{KERNEL_TITLE[k]} | {human(w)}", fontsize=8)
                ax.set_xlabel("start-address offset from 64 B line (bytes)")
                ax.set_ylabel("cycles / element")
        axs[0][0].legend(fontsize=6)
        fig.suptitle(f"Alignment ({t}); solid = x,y(,z) all shifted, dashed = only x shifted (median, IQR bars)")
        save(fig, a.fig, f"align_{t}")
    # ---- tail: x = n (categorical), y = cycles/element at offset 0
    tl = dt[(dt.offx == 0) & (dt.offy == 0) & (dt.n < 5000)].copy()
    kernels = [k for k in KERNEL_TITLE if k in set(tl.kernel)]
    if kernels:
        fig, axs = plt.subplots(2, 2, figsize=(11, 7), squeeze=False)
        vw = 64 // (8 if t == "f64" else 4)
        for ax, k in zip(axs.flat, kernels):
            g = tl[tl.kernel == k]
            ns = sorted(set(g.n))
            for b, gb in g.groupby("build"):
                gb = gb.sort_values("n")
                st = style(b)
                ax.plot(range(len(gb)), gb.cyc_per_elem_med, **st)
            ax.set_xticks(range(len(ns)))
            ax.set_xticklabels([str(x) + ("*" if x % vw else "") for x in ns], rotation=90, fontsize=6)
            ax.set_yscale("log")
            ax.set_xlabel(f"n elements  (* = n not a multiple of the 512-bit lane count {vw})")
            ax.set_ylabel("cycles / element")
            ax.set_title(KERNEL_TITLE[k], fontsize=10)
        for ax in list(axs.flat)[len(kernels):]:
            ax.set_visible(False)
        axs.flat[0].legend(fontsize=6)
        fig.suptitle(f"Tail handling ({t}, aligned): per-element cost vs n (median)")
        save(fig, a.fig, f"tail_{t}")
