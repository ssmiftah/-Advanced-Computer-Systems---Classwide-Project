#!/usr/bin/env python3
"""vec_check.py - vectorization verification (experiment 6).

Ground truth is the generated machine code (objdump of obj/rep_<build>.o, saved by the Makefile
in reports/<build>.objdump.txt); the compiler's own report (-fopt-info-vec-*) is summarized next to
it.  Outputs (all in reports/):
  vec_summary.csv   one row per build x kernel x type: class, widest register, loop instr counts
  vec_summary.md    tables + the compiler-report lines for each loop + the dot-product case study
  vec_snippets.md   concise inner-loop instruction snippets (xmm/ymm/zmm, vfmadd...) per build

Classification of the hottest loop of each function (loop = backward-branch region with most
packed arithmetic):
  scalar   : no packed arithmetic in the loop
  partial  : packed multiply but the FP additions stay serial scalar adds (in-order reduction:
             the compiler reported 'loop vectorized' but cannot reassociate the sum)
  vector   : packed arithmetic, no serial scalar FP adds
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REP = ROOT / "reports"
BUILDS = ["scalar", "scalar_znver5", "sse", "avx2", "znver5", "znver5_pv512",
          "sse_fm", "avx2_fm", "znver5_fm", "znver5_pv512_fm"]
KERNELS = ["saxpy", "dot", "mul", "stencil", "saxpy_stride", "dot_stride", "saxpy_gather", "dot_gather"]
TYPES = ["f32", "f64", "i32"]

PACKED = re.compile(r"^v?(add|sub|mul|fn?madd\d*|fn?msub\d*)p[sd]$|^v?p(add[dq]|mulld|muludq|muldq|mulq)$|^v?pmuludq$")
SCALAR_FP = re.compile(r"^v?(add|sub|mul|fn?madd\d*|fn?msub\d*)s[sd]$")
SCALAR_ADD = re.compile(r"^v?add s[sd]$".replace(" ", ""))
FMA = re.compile(r"^vfn?m(add|sub)\d*[ps][sd]$")
GATHER = re.compile(r"^vp?gather")
WIDTH = {"zmm": 64, "ymm": 32, "xmm": 16}


def parse_functions(path):
    funcs, cur = {}, None
    for line in path.read_text().splitlines():
        m = re.match(r"^[0-9a-f]+ <([^>]+)>:", line)
        if m:
            cur = m.group(1)
            funcs[cur] = []
            continue
        m = re.match(r"^\s+([0-9a-f]+):\t(\S+)\s*(.*)$", line)
        if m and cur:
            funcs[cur].append((int(m.group(1), 16), m.group(2), m.group(3).strip()))
    return funcs


def regwidth(ops):
    w = 0
    for r, v in WIDTH.items():
        if r in ops:
            w = max(w, v)
    return w


def best_loop(ins):
    """Return (start_idx, end_idx) of the backward-branch region with widest/most packed arithmetic."""
    addr_idx = {a: i for i, (a, _, _) in enumerate(ins)}
    best, bscore = None, (-1, -1, -1, -1)
    for j, (a, mn, ops) in enumerate(ins):
        if mn.startswith("j"):
            m = re.match(r"([0-9a-f]+) <", ops)
            if not m:
                continue
            t = int(m.group(1), 16)
            if t <= a and t in addr_idx:
                i = addr_idx[t]
                body = ins[i:j + 1]
                packed = sum(1 for _, x, _ in body if PACKED.match(x) or GATHER.match(x))
                scal = sum(1 for _, x, _ in body if SCALAR_FP.match(x))
                w = max([regwidth(o) for _, x, o in body if PACKED.match(x) or GATHER.match(x)] or [0])
                nomask = 0 if any('{%k' in o for _, _, o in body) else 1  # prefer unmasked main loop over masked epilogue
                score = (w, nomask, packed, scal * 1000 + len(body))
                if score > bscore:
                    best, bscore = (i, j), score
    return best


def analyse(ins, kernel, typ):
    loop = best_loop(ins)
    if loop is None:
        return dict(cls="scalar", width=0, packed=0, scalar=0, fma=0, gather=0, length=0, loop=None)
    body = ins[loop[0]:loop[1] + 1]
    packed = [x for x in body if PACKED.match(x[1]) or GATHER.match(x[1])]
    sc = [x for x in body if SCALAR_FP.match(x[1])]
    sadd = [x for x in body if re.match(r"^v?add s[sd]$".replace(" ", ""), x[1])]
    width = max([regwidth(o) for _, _, o in packed] or [0])
    if not packed:
        cls = "scalar"
    elif kernel.startswith("dot") and typ != "i32" and len(sadd) >= 2:
        cls = "partial"
    else:
        cls = "vector"
    return dict(cls=cls, width=width, packed=len(packed), scalar=len(sc),
                fma=sum(1 for x in body if FMA.match(x[1])),
                gather=sum(1 for x in body if GATHER.match(x[1])), length=len(body), loop=loop)


def loop_markers():
    m = {}
    for n, line in enumerate((ROOT / "src/kernels_impl.inc").read_text().splitlines(), 1):
        mm = re.search(r"LOOP:(\w+)", line)
        if mm:
            m[n] = mm.group(1)
    return m


def report_counts(build, markers):
    """Count 'loop vectorized' messages and 'couldn't vectorize' per kernel marker (3 types each)."""
    ok, miss = defaultdict(int), defaultdict(int)
    p = REP / f"{build}.vec-optimized.txt"
    if p.exists():
        for line in p.read_text().splitlines():
            m = re.match(r".*kernels_impl\.inc:(\d+):\d+: optimized: loop vectorized", line)
            if m and int(m.group(1)) in markers:
                ok[markers[int(m.group(1))]] += 1
    p = REP / f"{build}.vec-missed.txt"
    if p.exists():
        for line in p.read_text().splitlines():
            m = re.match(r".*kernels_impl\.inc:(\d+):\d+: missed: couldn't vectorize loop", line)
            if m and int(m.group(1)) in markers:
                miss[markers[int(m.group(1))]] += 1
    return ok, miss


def snippet(ins, loop, maxn=22):
    if loop is None:
        return ["(no loop found)"]
    body = ins[loop[0]:loop[1] + 1]
    lines = [f"{mn:<14}{ops}" for _, mn, ops in body]
    keep = [l for l in lines if ("mm" in l) or l.split()[0].startswith(("v", "mul", "add", "pmul"))]
    out = keep[:maxn]
    if len(keep) > maxn:
        out.append(f"... ({len(keep) - maxn} more)")
    out.append(f"[{len(body)} instrs in loop total, incl. address/loop-control]")
    return out


def main():
    if not (REP / "scalar.objdump.txt").exists():
        sys.exit("run `make vec-reports` first (reports/*.objdump.txt missing)")
    markers = loop_markers()
    rows, funcs_by_build = [], {}
    for b in BUILDS:
        p = REP / f"{b}.objdump.txt"
        if not p.exists():
            continue
        funcs = parse_functions(p)
        funcs_by_build[b] = funcs
        for k in KERNELS:
            for t in TYPES:
                ins = funcs.get(f"{k}_{t}")
                if ins is None:
                    continue
                a = analyse(ins, k, t)
                rows.append(dict(build=b, kernel=k, type=t, **{x: a[x] for x in
                                 ("cls", "width", "packed", "scalar", "fma", "gather", "length")}))
    with open(REP / "vec_summary.csv", "w") as f:
        cols = ["build", "kernel", "type", "cls", "width", "packed", "scalar", "fma", "gather", "length"]
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r[c]) for c in cols) + "\n")

    wname = {0: "-", 16: "xmm", 32: "ymm", 64: "zmm"}
    md = ["# Vectorization summary (generated by scripts/vec_check.py)\n",
          "Cell = class/widest vector register in the hottest loop (V=vector, P=partial: packed multiply but "
          "serial scalar adds, S=scalar), `+fma` if the loop contains FMA instructions.\n",
          "Source of truth: objdump of the compiled kernels (reports/<build>.objdump.txt).\n"]
    tab = {(r["build"], r["kernel"], r["type"]): r for r in rows}
    for t in TYPES:
        md.append(f"\n## type {t}\n")
        md.append("| build | " + " | ".join(KERNELS) + " |")
        md.append("|---|" + "---|" * len(KERNELS))
        for b in BUILDS:
            cells = []
            for k in KERNELS:
                r = tab.get((b, k, t))
                if not r:
                    cells.append("n/a")
                    continue
                c = {"vector": "V", "partial": "P", "scalar": "S"}[r["cls"]]
                s = f"{c}/{wname[r['width']]}" if c != "S" else "S"
                if r["fma"]:
                    s += "+fma"
                if r["gather"]:
                    s += "+gather"
                cells.append(s)
            md.append(f"| {b} | " + " | ".join(cells) + " |")

    def body_of(b):
        p = REP / f"{b}.objdump.txt"
        return [l for l in p.read_text().splitlines()[2:]] if p.exists() else None
    for a, b in (("znver5", "znver5_pv512"), ("znver5_fm", "znver5_pv512_fm")):
        x, y = body_of(a), body_of(b)
        if x and y:
            md.append(f"\n**{a} vs {b}: generated machine code is "
                      f"{'IDENTICAL' if x == y else 'DIFFERENT'}** "
                      f"(i.e. -mprefer-vector-width=512 is {'not needed' if x == y else 'needed'} with -march=znver5 on this GCC).\n")
    md.append("\n## Compiler report (-fopt-info-vec-*): messages per source loop (summed over f32/f64/i32)\n")
    names = list(dict.fromkeys(markers.values()))
    md.append("`ok/miss` = number of 'loop vectorized' / 'couldn't vectorize loop' messages. "
              "Each loop is instantiated for 3 types, and epilogues add extra 'ok' lines. "
              "NOTE: GCC reports 'loop vectorized' for the non-fast-math FP dot loop too, because it "
              "vectorizes the multiplies but keeps an in-order (serial) reduction - see case study.\n")
    md.append("| build | " + " | ".join(names) + " |")
    md.append("|---|" + "---|" * len(names))
    for b in BUILDS:
        ok, miss = report_counts(b, markers)
        md.append(f"| {b} | " + " | ".join(f"{ok[n]}/{miss[n]}" for n in names) + " |")

    # case study: FP dot reduction
    md.append("\n## Negative example: FP dot-product reduction without -fassociative-math\n")
    for b in ("sse", "znver5", "znver5_fm"):
        ins = funcs_by_build.get(b, {}).get("dot_f32")
        if not ins:
            continue
        a = analyse(ins, "dot", "f32")
        md.append(f"### {b}: dot_f32 -> class **{a['cls']}**, widest reg {wname[a['width']]}, "
                  f"loop: {a['packed']} packed arith, {a['scalar']} scalar FP arith\n")
        md.append("```\n" + "\n".join(snippet(ins, a["loop"])) + "\n```\n")
    md.append("Relevant lines of the compiler reports:\n```")
    for b in ("sse", "znver5", "znver5_fm"):
        p = REP / f"{b}.vec-optimized.txt"
        if p.exists():
            dl = [n for n, nm in markers.items() if nm == "dot"][0]
            for line in p.read_text().splitlines():
                if f"kernels_impl.inc:{dl}:" in line:
                    md.append(f"[{b}] {line}")
    md.append("```")
    (REP / "vec_summary.md").write_text("\n".join(md) + "\n")

    # snippets
    sn = ["# Inner-loop snippets (generated by scripts/vec_check.py)\n"]
    for b, k in [("scalar", "saxpy_f32"), ("sse", "saxpy_f32"), ("avx2", "saxpy_f32"),
                 ("znver5", "saxpy_f32"), ("znver5", "saxpy_f64"), ("znver5", "stencil_f32"),
                 ("sse", "dot_f32"), ("znver5", "dot_f32"), ("znver5_fm", "dot_f32"),
                 ("znver5", "saxpy_gather_f32"), ("znver5", "saxpy_stride_f32"),
                 ("sse", "saxpy_i32"), ("znver5", "saxpy_i32")]:
        ins = funcs_by_build.get(b, {}).get(k)
        if not ins:
            continue
        kk, tt = k.rsplit("_", 1)
        a = analyse(ins, kk, tt)
        sn.append(f"## {b} / {k}  (class={a['cls']}, widest={wname[a['width']]})\n")
        sn.append("```\n" + "\n".join(snippet(ins, a["loop"])) + "\n```\n")
    (REP / "vec_snippets.md").write_text("\n".join(sn) + "\n")
    print("wrote reports/vec_summary.{csv,md}, reports/vec_snippets.md")


if __name__ == "__main__":
    main()
