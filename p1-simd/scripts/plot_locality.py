#!/usr/bin/env python3
"""Experiment 2 figures: locality sweep (L1 -> L2 -> L3 -> DRAM): GiB/s and cycles/element."""
import matplotlib.pyplot as plt
from plot_common import *

ap = args(__doc__)
a = ap.parse_args()
d = load(a.proc, "locality_summary.csv")
d = d[(d.type == "f32") & (d.variant == "unit")]
kernels = [k for k in KERNEL_TITLE if k in set(d.kernel)]
for ycol, lo, hi, ylabel, name in [
        ("gibs_med", "gibs_q1", "gibs_q3", "algorithmic bandwidth (GiB/s)", "locality_gibs"),
        ("cyc_per_elem_med", "cyc_per_elem_q1", "cyc_per_elem_q3", "core cycles per element", "locality_cycles"),
        ("gflops_med", "gflops_q1", "gflops_q3", "throughput (GFLOP/s)", "locality_gflops")]:
    n = len(kernels)
    fig, axs = plt.subplots((n + 1) // 2, 2 if n > 1 else 1, figsize=(11, 3.6 * ((n + 1) // 2)), squeeze=False, sharex=True)
    for ax, k in zip(axs.flat, kernels):
        for b, g in d[d.kernel == k].groupby("build"):
            errline(ax, g, "ws_bytes", ycol, style(b), lo, hi)
        ax.set_yscale("log")
        ax.set_title(KERNEL_TITLE[k], fontsize=10)
        ax.set_ylabel(ylabel)
        size_axis(ax)
        cache_lines(ax)
    axs.flat[0].legend(fontsize=7)
    fig.suptitle("Locality sweep, float32, single thread (median, IQR band); GiB/s counts algorithmic bytes only")
    save(fig, a.fig, name)
