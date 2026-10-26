"""E1 -- which values does q0 have to hold?

For each program in programs/e1_obligation, HEIR compiles it with first-mod-bits equal to
  * the LoopRange bound on the OUTPUT only (obligation OUT),
  * the LoopRange bound on ALL values, every iteration (obligation ALL),
  * HEIR's own choice (first-mod-bits=0),
and the generated Lattigo code is run on every input set.  We also search the smallest
first-mod-bits that passes all our inputs.  If OUT passes while intermediate values exceed
q0/(2*Delta) by a large factor, intermediate wrap-around is harmless (Theorem 2).
"""
import glob, json, os, sys
from exp_common import *

PROG = os.path.join(HERE, "..", "programs", "e1_obligation")


def main():
    log = {"env": env_report(), "rows": []}
    print("\n".join(log["env"]))
    print(f"\n{'program':14s} {'LR OUT':>7s} {'LR ALL':>7s} {'HEIR auto':>14s} {'run @OUT':>14s} {'run @ALL':>10s} "
          f"{'run @OUT-1':>14s} {'smallest':>9s} {'max|intermediate|/cap(OUT)':>27s}")
    for f in sorted(glob.glob(os.path.join(PROG, "*.mlir"))):
        prog, b = bounds(f)
        lr = b["LoopRange"]
        ins = inputs_for(prog)
        qo, qa = lr["q0_out"], lr["q0_all"]
        r_auto = run(f, 0, "e1", ins)
        r_out = run(f, qo, "e1", ins, keep_ir=True)
        r_all = run(f, qa, "e1", ins)
        r_m1 = run(f, qo - 1, "e1", ins)
        r_47 = run(f, 47, "e1", ins)                 # the size that is enough for W1-W4
        small, tried = smallest_passing(f, "e1", ins, 45, qa)
        # how far beyond the OUT modulus' capacity do intermediate values go?
        cap = 2 ** (qo - SCALE - 1)                 # |v| < q0/(2 Delta), q0 ~ 2^qo
        ratio = float(lr["B_all"]) / cap
        row = dict(program=os.path.basename(f), q0_out=qo, q0_all=qa, B_out=float(lr["B_out"]),
                   B_all=float(lr["B_all"]), auto=r_auto, at_out=r_out, at_all=r_all, at_out_minus1=r_m1, at_47=r_47,
                   smallest=small, tried=tried, intermediate_over_cap=ratio)
        log["rows"].append(row)
        print(f"{row['program']:14s} {qo:7d} {qa:7d} {cell(r_auto):>14s} {cell(r_out):>14s} {cell(r_all):>10s} "
              f"{cell(r_m1):>14s} {str(small):>9s} {ratio:27.1f}")
        for r in (r_out, r_all, r_auto, r_m1, r_47):
            if r.get("max_err") is not None:
                print(f"      fmb={r['fmb']!s:>4}  q0={q0_of(r)}  status={r['status']:<10s} max|err|={r['max_err']:.3g}")
    out = os.path.join(HERE, "..", "results", "e1_obligation.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(log, open(out, "w"), indent=1, default=str)
    print("wrote", out)


if __name__ == "__main__":
    main()
