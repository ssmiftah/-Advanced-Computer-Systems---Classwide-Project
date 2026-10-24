#!/usr/bin/env python3
"""process.py - raw per-sample CSVs -> per-configuration summaries (median / IQR) and speedups.

Usage (from the repo root):
  common/pyrun.sh p1-simd/scripts/process.py --raw p1-simd/data/raw --out p1-simd/data/processed

For every experiment csv in <raw>/<exp>/<exp>.csv writes
  <out>/<exp>_summary.csv  one row per configuration: median, q1, q3, min, max of the per-call time
                           and of every derived metric (computed per sample, then summarised)
  <out>/<exp>_speedup.csv  same keys, with speedup of each build over the 'scalar' build:
                           speedup = median(t_scalar) / median(t_build)   (same kernel/type/size/knobs)
                           (+ IQR-propagated bounds: q1/q3 ratios of the two builds' medians are NOT
                           formed; instead lo/hi use scalar median over build q3/q1 time)
and from <raw>/bandwidth/*.csv
  <out>/bandwidth_summary.csv   median GiB/s (+IQR) per mode and buffer size
  <out>/peakflops_summary.csv   median GFLOP/s, FLOP/cycle, GHz per vector width
Directories named 'sanity' under <raw> are ignored unless --raw points at them.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

KEYS = ["exp", "build", "kernel", "type", "variant", "n", "n_mod_vw", "stride", "gather",
        "offx", "offy", "offz", "mis_x", "mis_y", "ws_bytes", "flops", "bytes_nominal"]
# NOTE: 'reps' (calibrated K) is deliberately NOT a key: it can differ between the repeated
# invocations of one configuration (scripts/common.sh REPEATS), which must be pooled.
METRICS = ["ns_per_call", "gflops", "gibs", "cyc_per_elem", "ghz"]


def q1(s): return s.quantile(0.25)
def q3(s): return s.quantile(0.75)


def summarise(df, keys, metrics):
    g = df.groupby(keys, dropna=False)
    parts = []
    for m in metrics:
        a = g[m].agg(["median", q1, q3, "min", "max"])
        a.columns = [f"{m}_{c}" for c in ["med", "q1", "q3", "min", "max"]]
        parts.append(a)
    out = pd.concat(parts, axis=1)
    out["n_samples"] = g.size()
    if "seed" in df.columns:
        out["n_runs"] = g["seed"].nunique()
    return out.reset_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="p1-simd/data/raw")
    ap.add_argument("--out", default="p1-simd/data/processed")
    a = ap.parse_args()
    raw, out = Path(a.raw), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for d in sorted(p for p in raw.iterdir() if p.is_dir() and p.name != "sanity"):
        exp = d.name
        if exp == "bandwidth":
            for mode in ("read", "triad"):
                f = d / f"membw_{mode}.csv"
                if f.exists():
                    df = pd.read_csv(f)
                    s = summarise(df, ["mode", "size_kib"], ["gibs", "ghz"])
                    s.to_csv(out / f"bandwidth_{mode}_summary.csv", index=False)
            f = d / "peakflops.csv"
            if f.exists():
                df = pd.read_csv(f)
                summarise(df, ["kind"], ["gflops", "flop_per_cycle", "ghz"]).to_csv(
                    out / "peakflops_summary.csv", index=False)
            continue
        f = d / f"{exp}.csv"
        if not f.exists():
            continue
        df = pd.read_csv(f)
        df = df[df.ns_per_call > 0]
        s = summarise(df, KEYS, METRICS)
        s.to_csv(out / f"{exp}_summary.csv", index=False)
        base_keys = [k for k in KEYS if k not in ("build", "mis_x", "mis_y")]
        sc = s[s.build == "scalar"][base_keys + ["ns_per_call_med", "gflops_med"]].rename(
            columns={"ns_per_call_med": "scalar_ns", "gflops_med": "scalar_gflops"})
        m = s.merge(sc, on=base_keys, how="left")
        m["speedup"] = m.scalar_ns / m.ns_per_call_med
        m["speedup_lo"] = m.scalar_ns / m.ns_per_call_q3   # slow end of the build's IQR
        m["speedup_hi"] = m.scalar_ns / m.ns_per_call_q1
        m.to_csv(out / f"{exp}_speedup.csv", index=False)
        print(f"{exp}: {len(df)} samples -> {len(s)} configs")


if __name__ == "__main__":
    main()
