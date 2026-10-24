"""Aggregate raw repetitions into medians / IQR / std.

Usage (from the repo root):
    common/pyrun.sh p2-memory/scripts/process.py p2-memory/data/raw/sanity p2-memory/data/processed/sanity

For every raw CSV <raw>/<experiment>/<name>.csv the rows are grouped by all
configuration columns (everything that is not a measurement and not `rep`) and each
measurement column gets _median, _q1, _q3, _std, _min, _max and a row count `n`.
Raw files are never modified. Extra products:
  latency/zero_queue_table.csv  per-level ns (median, IQR), measured core GHz, cycles
  kernel/kernel_joined.csv      kernel time per element + perf counters per element
  tlb/tlb_joined.csv            ns per access + dTLB counters per access
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MEASURES = {
    "ns_per_access", "core_ghz", "seconds", "useful_GBps", "useful_GiBps", "line_GBps",
    "est_mem_GBps", "thr_min_GBps", "thr_max_GBps", "lat_ns_mean", "lat_ns_min", "lat_ns_max",
    "chase_GBps", "bg_GBps", "bg_est_mem_GBps", "total_GBps", "outstanding_littles",
    "ns_per_elem", "thp_frac",
}
SKIP_KEYS = {"rep"}
# Representative size per level: well inside the level but large enough that the next-smaller
# level holds only a small fraction of the nodes (a random chase over S bytes hits a cache of
# capacity C < S with probability ~C/S): L2 768 KiB (6% L1 hits), L3 16 MiB (6% L2 hits,
# half of the 32 MiB per-CCD L3), DRAM 1 GiB (3% L3 hits; 512 THP entries fit the L2 dTLB).
LEVELS = [("L1", 16 * 1024), ("L2", 768 * 1024), ("L3", 16 * 2**20), ("DRAM", 2**30)]


def q1(x):
    return np.nanpercentile(x, 25)


def q3(x):
    return np.nanpercentile(x, 75)


def aggregate(df, drop_keys=()):
    df = df.copy()
    if "core_ghz" in df:
        df.loc[df["core_ghz"] <= 0, "core_ghz"] = np.nan
    meas = [c for c in df.columns if c in MEASURES]
    keys = [c for c in df.columns if c not in MEASURES and c not in SKIP_KEYS
            and c not in drop_keys and c not in ("elems", "steps", "passes")]
    g = df.groupby(keys, dropna=False, sort=False)
    out = g[meas].agg(["median", q1, q3, "std", "min", "max"])
    out.columns = [f"{m}_{'q1' if s == 'q1' else 'q3' if s == 'q3' else s}" for m, s in out.columns]
    out["n"] = g.size()
    return out.reset_index()


def zero_queue_table(proc):
    df = proc[(proc["pattern"] == "random") & (proc["stride"] == 64)]
    rows = []
    for pages in sorted(df["pages"].unique()):
        d = df[df["pages"] == pages]
        for name, target in LEVELS:
            r = d.iloc[(np.log(d["size_bytes"]) - np.log(target)).abs().argsort()[:1]]
            if r.empty:
                continue
            r = r.iloc[0]
            ns, ghz = r["ns_per_access_median"], r["core_ghz_median"]
            rows.append(dict(level=name, pages=pages, size_bytes=int(r["size_bytes"]),
                             ns_median=ns, ns_q1=r["ns_per_access_q1"], ns_q3=r["ns_per_access_q3"],
                             core_ghz=ghz, cycles=ns * ghz, n=int(r["n"])))
    return pd.DataFrame(rows)


def pivot_perf(perf, keys):
    perf = perf.copy()
    perf["per_work"] = perf["count"] / perf["total_work"]
    p = perf.pivot_table(index=keys, columns="event", values="per_work", aggfunc="median")
    p.columns = [f"{c}_per_work" for c in p.columns]
    return p.reset_index()


def main(raw, out):
    raw, out = Path(raw), Path(out)
    for exp in sorted(p for p in raw.iterdir() if p.is_dir()):
        (out / exp.name).mkdir(parents=True, exist_ok=True)
        for f in sorted(exp.glob("*.csv")):
            df = pd.read_csv(f)
            if f.name.endswith("_perf.csv"):
                continue
            proc = aggregate(df, drop_keys=("evset",) if "evset" in df else ())
            proc.to_csv(out / exp.name / f.name, index=False)
            print(f"{exp.name}/{f.name}: {len(df)} raw rows -> {len(proc)} points")
            if exp.name == "latency" and f.name == "latency.csv":
                zero_queue_table(proc).to_csv(out / exp.name / "zero_queue_table.csv", index=False)
            for kind, perfname, keys in (
                ("kernel", "kernel_perf.csv", ["kernel", "pattern", "stride_blocks", "block_elems", "pages", "footprint"]),
                ("tlb", "tlb_perf.csv", ["span_bytes", "stride", "pages", "order"]),
            ):
                if exp.name == kind and f.name == f"{kind}.csv" and (exp / perfname).exists():
                    perf = pivot_perf(pd.read_csv(exp / perfname), keys)
                    # cycles appear in both kernel event sets: keep one column
                    joined = proc.merge(perf, on=keys, how="left")
                    joined.to_csv(out / exp.name / f"{kind}_joined.csv", index=False)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
