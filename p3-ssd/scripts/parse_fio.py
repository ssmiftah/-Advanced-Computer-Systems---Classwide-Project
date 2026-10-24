#!/usr/bin/env python3
"""Parse fio json+ output (data/raw/<exp>/*.json + *.params sidecars) into tidy CSVs.

Outputs (in PROC_DIR, default p3-ssd/data/processed):
  runs.csv  one row per fio run (experiment, label, rep, knobs, metrics for read/write/total)
  agg.csv   mean/std over repeats per (exp, label)

Units: bw_MBps = 1e6 bytes/s (decimal MB), bw_MiBps = 2^20 bytes/s. Latencies in microseconds.
lat_* = total latency (submission+completion), clat_* = completion latency (percentiles are clat).
'tot_' columns combine read+write: iops sum, bytes/s sum, IOPS-weighted mean latency.
outstanding_eff = tot_iops * tot_lat_mean_us * 1e-6  (Little's Law: L = lambda * W).
Env: RAW_DIR, PROC_DIR.
"""
import json, os, sys, glob, re
import numpy as np, pandas as pd

P3 = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_Q = os.path.join(P3, "scratch", "sanity") if os.environ.get("QUICK") == "1" else None  # same rule as common.sh
RAW = os.environ.get("RAW_DIR", os.path.join(_Q, "raw") if _Q else os.path.join(P3, "data", "raw"))
PROC = os.environ.get("PROC_DIR", os.path.join(_Q, "processed") if _Q else os.path.join(P3, "data", "processed"))
PCTS = ["50", "95", "99", "99.9", "99.99"]


def to_bytes(s):
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kKmMgG]?)", str(s))
    return int(float(m.group(1)) * {"": 1, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30}[m.group(2).lower()])


def read_json(path):
    txt = open(path).read()
    return json.loads(txt[txt.index("{"):])


def pct(d, p):
    for k, v in d.get("percentile", {}).items():
        if abs(float(k) - float(p)) < 1e-6:
            return v / 1000.0
    return np.nan


def dir_metrics(j, pre):
    out = {}
    out[pre + "iops"] = j["iops"]
    out[pre + "bw_MBps"] = j["bw_bytes"] / 1e6
    out[pre + "bw_MiBps"] = j["bw_bytes"] / 2**20
    out[pre + "ios"] = j["total_ios"]
    out[pre + "io_GiB"] = j["io_bytes"] / 2**30   # bytes moved in the measured window (post-ramp)
    c, l = j.get("clat_ns", {}), j.get("lat_ns", {})
    if j["total_ios"] == 0:  # direction not exercised
        c, l = {}, {}
    out[pre + "lat_mean_us"] = l.get("mean", np.nan) / 1000 if l else np.nan
    out[pre + "clat_mean_us"] = c.get("mean", np.nan) / 1000 if c else np.nan
    out[pre + "clat_std_us"] = c.get("stddev", np.nan) / 1000 if c else np.nan
    out[pre + "clat_max_us"] = c.get("max", np.nan) / 1000 if c else np.nan
    for p in PCTS:
        out[pre + "clat_p" + p + "_us"] = pct(c, p) if c else np.nan
    return out


def parse_run(jpath):
    ppath = jpath[:-5] + ".params"
    if not os.path.exists(ppath):
        return None
    par = dict(l.rstrip("\n").split("=", 1) for l in open(ppath) if "=" in l)
    try:
        d = read_json(jpath)
    except Exception as e:
        print("skip (bad json)", jpath, e, file=sys.stderr); return None
    j = d["jobs"][0]
    row = {"exp": par["exp"], "label": par["label"], "rep": int(par["rep"]),
           "rw": par["RW"], "rwmix": int(par["RWMIX"]) if "randrw" in par["RW"] or par["RW"] == "rw" else (100 if "read" in par["RW"] else 0),
           "bs": par["BS"], "bs_bytes": to_bytes(par["BS"]), "iodepth": int(par["IODEPTH"]),
           "numjobs": int(par["NUMJOBS"]), "direct": int(par["DIRECT"]), "ioengine": par["IOENGINE"],
           "span": par["SPAN"], "span_bytes": to_bytes(par["SPAN"]), "compress_pct": int(par["COMPRESS"]),
           "runtime_s": int(par["RUNTIME"]), "ramp_s": int(par["RAMP"]), "cpus": par["CPUS"],
           "temp_start_c": float(par["temp_start"]), "temp_end_c": float(par["temp_end"]),
           "fio_rc": int(par["fio_rc"]), "file": os.path.relpath(jpath, RAW),
           # actual measured duration: write jobs are size-capped and may end before RUNTIME
           "job_runtime_s": j["job_runtime"] / 1000.0}
    for k, v in par.items():  # extra metadata (SERIES, PATTERN, DEMO, ...)
        if k.isupper() and k not in ("BS", "BWLOG", "COMPRESS", "CPUS", "DIRECT", "ENDFSYNC", "IODEPTH", "IOENGINE", "NUMJOBS",
                                     "OFFSET", "RAMP", "RATE", "REPS", "RUNTIME", "RW", "RWMIX", "SPAN"):
            row[k.lower()] = v
    row["outstanding_cfg"] = row["iodepth"] * row["numjobs"]
    row.update(dir_metrics(j["read"], "r_")); row.update(dir_metrics(j["write"], "w_"))
    ri, wi = row["r_iops"], row["w_iops"]
    row["tot_iops"] = ri + wi
    row["tot_bw_MBps"] = row["r_bw_MBps"] + row["w_bw_MBps"]
    row["tot_bw_MiBps"] = row["r_bw_MiBps"] + row["w_bw_MiBps"]
    lat = 0.0
    for pre, i in (("r_", ri), ("w_", wi)):
        if i > 0 and not np.isnan(row[pre + "lat_mean_us"]):
            lat += i * row[pre + "lat_mean_us"]
    row["tot_lat_mean_us"] = lat / row["tot_iops"] if row["tot_iops"] > 0 else np.nan
    row["outstanding_eff"] = row["tot_iops"] * row["tot_lat_mean_us"] * 1e-6
    row["pattern"] = row.get("pattern", "sequential" if row["rw"] in ("read", "write", "rw") else "random")
    return row


def main():
    rows = []
    for jp in sorted(glob.glob(os.path.join(RAW, "*", "*.json"))):
        if os.sep + "prepare" + os.sep in jp:
            continue
        r = parse_run(jp)
        if r: rows.append(r)
    if not rows:
        sys.exit("no runs found under " + RAW)
    df = pd.DataFrame(rows)
    bad = df[(df.fio_rc != 0) | ((df.r_ios + df.w_ios) == 0)]
    for _, b in bad.iterrows():
        print(f"WARNING: {b.file}: fio_rc={b.fio_rc}, ios={b.r_ios + b.w_ios} (excluded)", file=sys.stderr)
    df = df.drop(bad.index)
    print(f"measured-window writes in parsed runs: {df.w_io_GiB.sum():.1f} GiB (excludes ramp and the test-file fill)")
    os.makedirs(PROC, exist_ok=True)
    df.to_csv(os.path.join(PROC, "runs.csv"), index=False)
    num = [c for c in df.columns if df[c].dtype.kind in "fi" and c not in ("rep",)]
    keep = [c for c in df.columns if c not in num and c not in ("rep", "file", "exp", "label")]
    g = df.groupby(["exp", "label"], sort=False)
    agg = g[keep].first()
    agg["n_reps"] = g.size()
    for c in num:
        agg[c + "_mean"] = g[c].mean(); agg[c + "_std"] = g[c].std(ddof=1).fillna(0.0)
    # knob columns are constant within a group: expose them without suffix too
    for c in ["iodepth", "numjobs", "bs_bytes", "span_bytes", "rwmix", "direct", "compress_pct", "outstanding_cfg"]:
        agg[c] = g[c].first()
    agg = agg.reset_index()
    agg.to_csv(os.path.join(PROC, "agg.csv"), index=False)
    print(f"parsed {len(df)} runs -> {PROC}/runs.csv, {len(agg)} points -> agg.csv")


if __name__ == "__main__":
    main()
