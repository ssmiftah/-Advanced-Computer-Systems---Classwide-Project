"""Turn one `perf stat -x,` run into long-format rows (one per event).

Joins the perf counts with the program's own CSV (the config columns of its first row
and the total amount of work = sum of --work-col over its rows), so counters can later
be normalised per element / per access.

Output columns: <config columns of the program CSV>, [extra --kv], event, count,
run_pct (perf's multiplexing fraction, 100 = counted the whole time), total_work.
Append-only; a header is written when the file is new.
"""
import argparse
import csv
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--perf", required=True)
    ap.add_argument("--prog", required=True)
    ap.add_argument("--work-col", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--kv", nargs="*", default=[], help="extra key=value columns")
    a = ap.parse_args()

    with open(a.prog) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"no program rows in {a.prog}")
    drop = {"rep", "seconds", "ns_per_elem", "ns_per_access", "useful_GBps", "passes", "elems", "steps"}
    cfg = {k: v for k, v in rows[0].items() if k not in drop}
    for kv in a.kv:
        k, v = kv.split("=", 1)
        cfg[k] = v
    work = sum(float(r[a.work_col]) for r in rows)

    events = []
    with open(a.perf) as f:
        for line in f:
            p = line.rstrip("\n").split(",")
            if len(p) < 5 or line.startswith("#"):
                continue
            val, ev, pct = p[0], p[2], p[4]
            if not val.replace(".", "").isdigit():  # <not counted>/<not supported>
                val = "nan"
            events.append((ev.removesuffix(":u"), val, pct))

    new = not os.path.exists(a.out) or os.path.getsize(a.out) == 0
    with open(a.out, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(list(cfg) + ["event", "count", "run_pct", "total_work"])
        for ev, val, pct in events:
            w.writerow(list(cfg.values()) + [ev, val, pct, f"{work:.0f}"])


if __name__ == "__main__":
    main()
