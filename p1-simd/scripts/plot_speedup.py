#!/usr/bin/env python3
"""Experiment 1 figures: speedup over scalar, GFLOP/s and cycles/element vs working-set size."""
import matplotlib.pyplot as plt
from plot_common import *

ap = args(__doc__)
a = ap.parse_args()
d = load(a.proc, "speedup_speedup.csv")
d = d[(d.type == "f32") & (d.variant == "unit")]
kernels = [k for k in KERNEL_TITLE if k in set(d.kernel)]
for ycol, lo, hi, ylabel, name, logy in [
        ("speedup", "speedup_lo", "speedup_hi", "speedup over scalar build (x)", "speedup_vs_size", True),
        ("gflops_med", "gflops_q1", "gflops_q3", "throughput (GFLOP/s)", "speedup_gflops", True),
        ("cyc_per_elem_med", "cyc_per_elem_q1", "cyc_per_elem_q3", "core cycles per element", "speedup_cycles", True)]:
    fig, axs = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    for ax, k in zip(axs.flat, kernels):
        for b, g in d[d.kernel == k].groupby("build"):
            errline(ax, g, "ws_bytes", ycol, style(b), lo, hi)
        if ycol == "speedup":
            ax.axhline(1, color="0.5", lw=0.8)
        ax.set_title(KERNEL_TITLE[k], fontsize=10)
        ax.set_ylabel(ylabel)
        if logy:
            ax.set_yscale("log")
        size_axis(ax)
        cache_lines(ax)
    axs.flat[0].legend(fontsize=7)
    fig.suptitle(f"Scalar vs auto-vectorized, float32, unit stride, aligned (median, IQR band)")
    save(fig, a.fig, name)
