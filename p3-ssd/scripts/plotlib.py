"""Shared plotting helpers (Okabe-Ito palette, PNG+PDF output, agg.csv loader)."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, pandas as pd

P3 = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_Q = os.path.join(P3, "scratch", "sanity") if os.environ.get("QUICK") == "1" else None  # same rule as common.sh
RAW = os.environ.get("RAW_DIR", os.path.join(_Q, "raw") if _Q else os.path.join(P3, "data", "raw"))
PROC = os.environ.get("PROC_DIR", os.path.join(_Q, "processed") if _Q else os.path.join(P3, "data", "processed"))
FIG = os.environ.get("FIG_DIR", os.path.join(_Q, "figures") if _Q else os.path.join(P3, "figures"))
C = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73", "red": "#D55E00",
     "purple": "#CC79A7", "sky": "#56B4E9", "grey": "#666666", "yellow": "#B8A100"}
CL = list(C.values())
plt.rcParams.update({"figure.dpi": 110, "savefig.dpi": 200, "axes.grid": True, "grid.alpha": 0.3,
                     "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
                     "axes.prop_cycle": matplotlib.cycler(color=CL)})


def agg(exp=None):
    p = os.path.join(PROC, "agg.csv")
    if not os.path.exists(p):
        raise SystemExit("run parse_fio.py first (missing %s)" % p)
    df = pd.read_csv(p)
    if exp is not None:
        df = df[df.exp == exp].copy()
        if df.empty:
            raise SystemExit(f"no data for experiment '{exp}' in {p}; skipping")
    return df


def save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(FIG, f"{name}.{ext}"))
    plt.close(fig)
    print("wrote", os.path.join(FIG, name + ".png"))


def table_out(df, name):
    os.makedirs(FIG, exist_ok=True)
    df.to_csv(os.path.join(FIG, name + ".csv"), index=False)
    with open(os.path.join(FIG, name + ".md"), "w") as f:
        f.write(md_table(df))
    print("wrote", os.path.join(FIG, name + ".csv/.md"))


def md_table(df):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(("%.4g" % v if isinstance(v, float) else str(v)) for v in r) + " |")
    return "\n".join(out) + "\n"


def bs_label(b):
    b = int(b)
    return f"{b//1024}K" if b < 1 << 20 else f"{b//(1<<20)}M"


def err(df, col):
    return df[col + "_std"].values if col + "_std" in df else None


def exit_if_missing(fn):
    """Run fn(); turn the 'no data' SystemExit into a clean message."""
    try:
        fn()
    except SystemExit as e:
        print(e)
