"""plot_common.py - shared helpers for the P1 plot scripts (import-only)."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# L1d 48 KiB, L2 1 MiB per core, L3 32 MiB per CCD (Ryzen 9 9950X); x axis = nominal footprint of
# all arrays touched by the kernel (bytes).
CACHE_LINES = [(48 * 1024, "L1d 48K"), (1024 * 1024, "L2 1M"), (32 * 1024 * 1024, "L3 32M")]

# Okabe-Ito colour-blind-safe palette, one fixed colour/marker per build.
BUILD_STYLE = {
    "scalar": ("#000000", "o", "scalar (-O3 no-vec)"),
    "scalar_znver5": ("#999999", "o", "scalar, -march=znver5 (no-vec, FMA)"),
    "sse": ("#E69F00", "s", "SSE2 auto-vec (-O3)"),
    "avx2": ("#56B4E9", "^", "AVX2+FMA (-mavx2 -mfma)"),
    "znver5": ("#009E73", "D", "znver5 (AVX-512)"),
    "znver5_pv512": ("#117733", "d", "znver5 + pv512"),
    "sse_fm": ("#D55E00", "s", "SSE2 + assoc-math"),
    "avx2_fm": ("#0072B2", "^", "AVX2 + assoc-math"),
    "znver5_fm": ("#CC79A7", "D", "znver5 + assoc-math"),
    "znver5_pv512_fm": ("#882255", "d", "znver5 pv512 + assoc-math"),
}
KERNEL_TITLE = {"saxpy": "SAXPY  y=a*x+y", "dot": "dot  s=sum x*y", "mul": "multiply  z=x*y",
                "stencil": "3-pt stencil"}


def args(desc):
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("--proc", default="p1-simd/data/processed", help="dir with *_summary.csv")
    ap.add_argument("--fig", default="p1-simd/figures", help="output dir for PNG+PDF")
    return ap


def load(proc, name):
    f = Path(proc) / name
    if not f.exists():
        raise SystemExit(f"missing {f}; run process.py first")
    return pd.read_csv(f)


def cache_lines(ax, ymax_frac=0.98):
    for x, lab in CACHE_LINES:
        ax.axvline(x, color="0.55", ls=":", lw=1)
        ax.text(x, ax.get_ylim()[1], " " + lab, rotation=90, va="top", ha="right", fontsize=7, color="0.35")


def size_axis(ax):
    ax.set_xscale("log", base=2)
    ax.set_xlabel("working-set footprint (bytes, all arrays)")
    ticks = [2 ** k for k in range(12, 31, 3)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([human(t) for t in ticks])
    ax.minorticks_off()


def human(b):
    for s, u in ((2 ** 30, "GiB"), (2 ** 20, "MiB"), (2 ** 10, "KiB")):
        if b >= s:
            return f"{b / s:g} {u}"
    return f"{b} B"


def style(b):
    c, m, lab = BUILD_STYLE.get(b, ("gray", "x", b))
    return dict(color=c, marker=m, label=lab, ms=4, lw=1.2)


def save(fig, figdir, name):
    d = Path(figdir)
    d.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(d / f"{name}.{ext}", dpi=160)
    plt.close(fig)
    print(f"wrote {d / name}.png/.pdf")


def errline(ax, g, xcol, ycol, st, lo=None, hi=None):
    """Median line with IQR band (lo/hi columns are the q1/q3 of the same metric)."""
    g = g.sort_values(xcol)
    ax.plot(g[xcol], g[ycol], **st)
    if lo and hi:
        ax.fill_between(g[xcol], g[lo], g[hi], color=st["color"], alpha=0.2, lw=0)
