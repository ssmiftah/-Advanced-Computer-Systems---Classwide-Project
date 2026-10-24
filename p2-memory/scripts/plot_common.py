"""Shared plotting helpers (matplotlib, Okabe-Ito colour-blind-safe palette)."""
import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#000000"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X"]
KIB, MIB = 1024, 1024**2
# Cache capacities of this machine (Ryzen 9 9950X): L1d 48 KiB, L2 1 MiB, L3 32 MiB per CCD.
CACHE_LINES = [(48 * KIB, "L1d 48 KiB"), (1 * MIB, "L2 1 MiB"), (32 * MIB, "L3 32 MiB/CCD")]

plt.rcParams.update({
    "figure.dpi": 110, "axes.grid": True, "grid.alpha": 0.25, "axes.spines.top": False,
    "axes.spines.right": False, "font.size": 10, "legend.frameon": False,
    "axes.prop_cycle": matplotlib.cycler(color=COLORS),
})


def args(default_exp=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/processed/sanity", help="processed dir")
    ap.add_argument("--out", default="figures/sanity", help="figure dir")
    a = ap.parse_args()
    a.inp, a.out = Path(a.inp), Path(a.out)
    a.out.mkdir(parents=True, exist_ok=True)
    return a


def load(a, exp, name):
    p = a.inp / exp / name
    if not p.exists():
        print(f"skip: {p} missing")
        return None
    return pd.read_csv(p)


def save(fig, a, name):
    for ext in ("png", "pdf"):
        fig.savefig(a.out / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print("wrote", a.out / f"{name}.png")


def size_axis(ax, ymax_text=True):
    """log-x size axis with vertical lines at the cache capacities."""
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_locator(matplotlib.ticker.FixedLocator([2**p for p in range(12, 33, 4)]))
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: fmt_size(v)))
    lo, hi = ax.get_ylim()
    for x, lab in CACHE_LINES:
        ax.axvline(x, color="gray", ls="--", lw=0.9)
        ax.text(x, 1.01, lab, transform=ax.get_xaxis_transform(), rotation=0, ha="center",
                va="bottom", fontsize=8, color="dimgray")
    ax.set_xlabel("working-set size (log scale)")


def fmt_size(v):
    for unit, d in (("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10)):
        if v >= d:
            return f"{v / d:g} {unit}"
    return f"{v:g} B"


def errline(ax, x, med, lo, hi, label, i, **kw):
    ax.errorbar(x, med, yerr=[np.maximum(med - lo, 0), np.maximum(hi - med, 0)], label=label,
                color=COLORS[i % len(COLORS)], marker=MARKERS[i % len(MARKERS)], ms=4, lw=1.4,
                capsize=2, **kw)
