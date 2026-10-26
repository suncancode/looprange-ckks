"""E2 -- the W20 Table 2 programs again, now with every column defined precisely.

For each program the q0 (bits) chosen by each analysis is passed to HEIR as first-mod-bits,
HEIR generates Lattigo code, and the code is run on every input set.  Columns:
  HEIR auto      first-mod-bits=0 (HEIR's own range analysis; bounds every level-0 value)
  simple fix     HEIR's scalar rules with |a-b| <= Ba+Bb, OUTPUT obligation
  interval       signed interval analysis, OUTPUT obligation
  LR OUT         LoopRange, bound on the returned value only (what W20 Table 2 used)
  LR ALL         LoopRange, bound on every value in every iteration
  smallest       smallest first-mod-bits (from 45 up) that is correct on all our inputs
"""
import glob, json, os, sys
from exp_common import *

SRC = os.path.join(HERE, "..", "programs", "w20_table2")
NS = [int(x) for x in os.environ.get("E2_NS", "1 2 3 5 20").split()]


def programs():
    out = []
    for f in ("sub.mlir", "mulsub.mlir"):
        out.append(os.path.join(SRC, f))
    gen = os.path.join(HERE, "..", "programs", "generated"); os.makedirs(gen, exist_ok=True)
    for t in ("loop_alt", "relax"):
        tmpl = open(os.path.join(SRC, t + ".mlir.in")).read()
        for n in NS:
            p = os.path.join(gen, f"{t}_n{n}.mlir"); open(p, "w").write(tmpl.replace("@N@", str(n)))
            out.append(p)
    return out


def main():
    log = {"env": env_report(), "rows": []}
    print("\n".join(log["env"]))
    hdr = f"{'program':16s} {'HEIR auto':>14s} {'simple fix':>11s} {'interval':>10s} {'LR OUT':>8s} {'LR ALL':>8s} {'smallest':>9s}  B_out / B_all (LoopRange)"
    print("\n" + hdr)
    for f in programs():
        prog, b = bounds(f)
        ins = inputs_for(prog)
        cols = {}
        cols["auto"] = run(f, 0, "e2", ins)
        for key, name, ob in (("simple", "simple fix", "q0_out"), ("interval", "signed interval", "q0_out"),
                              ("lr_out", "LoopRange", "q0_out"), ("lr_all", "LoopRange", "q0_all")):
            cols[key] = run(f, b[name][ob], "e2", ins)
        hi = max(b["LoopRange"]["q0_all"], b["LoopRange"]["q0_out"])
        small, tried = smallest_passing(f, "e2", ins, 45, hi)
        lr = b["LoopRange"]
        row = dict(program=os.path.basename(f), bounds={k: {kk: (float(vv) if hasattr(vv, "numerator") else vv)
                                                           for kk, vv in v.items()} for k, v in b.items()},
                   runs=cols, smallest=small, tried=tried)
        log["rows"].append(row)
        print(f"{row['program'][:-5]:16s} {cell(cols['auto']):>14s} {cell(cols['simple']):>11s} {cell(cols['interval']):>10s} "
              f"{cell(cols['lr_out']):>8s} {cell(cols['lr_all']):>8s} {str(small):>9s}  {float(lr['B_out']):.4g} / {float(lr['B_all']):.4g}  [{lr['mode']}]")
    errs_ok = [r["max_err"] for row in log["rows"] for r in row["runs"].values() if r.get("status") == "OK"]
    errs_bad = [r["max_err"] for row in log["rows"] for r in row["runs"].values() if str(r.get("status", "")).startswith("WRONG")]
    print(f"\nlargest error among OK runs: {max(errs_ok):.3g};  smallest error among WRONG runs: "
          f"{min(errs_bad) if errs_bad else float('nan'):.3g}   (tolerance 1e-3 * max(1, |expected|))")
    out = os.path.join(HERE, "..", "results", "e2_table.json")
    json.dump(log, open(out, "w"), indent=1, default=str); print("wrote", out)


if __name__ == "__main__":
    main()
