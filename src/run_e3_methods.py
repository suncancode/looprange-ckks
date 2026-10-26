"""E3 -- LoopRange against the simple subtraction fix, signed interval analysis and standard
affine arithmetic (and HEIR as implemented), on ten loop kernels.  Plaintext analysis only
(no encryption): the question is how large a bound each method can PROVE and at what cost.

For n in {10, 100, 1000} (static) and '?' (dynamic trip count) we print, per method, the
q0 bits from the OUTPUT bound (HEIR's rule scale + ceil(log2 B) + 2), or 'n.e.' when the
method cannot establish a bound, and the number of loop-body evaluations.  For n = 10 we
also run every kernel exactly on a grid of inputs and report the largest |output| actually
reached, so that unsound bounds (below the observed value) are visible.
"""
import glob, json, os, sys, time, itertools
from fractions import Fraction as F
from exp_common import HERE, SCALE
sys.path.insert(0, os.path.join(HERE, "looprange3"))
from mlir_reader import read
from analysis import analyze, q0_bits, METHODS
import concrete

KDIR = os.path.join(HERE, "..", "programs", "e3_kernels")
GEN = os.path.join(HERE, "..", "programs", "generated", "e3"); os.makedirs(GEN, exist_ok=True)
NS = ["10", "100", "1000", "?"]
SHOW = ["HEIR (as implemented)", "simple fix", "signed interval", "standard affine (unrolled)",
        "simple fix + invariant", "interval + invariant", "LoopRange"]


def observed_max(prog, grid=9):
    ins = prog.inputs(); best = F(0)
    pts = [[o.lo + (o.hi - o.lo) * F(i, grid - 1) for i in range(grid)] for o in ins]
    for c in itertools.product(*pts):
        for pattern in ("uniform", "alternating"):
            if prog.slots == 1 and pattern == "alternating": continue
            vals = {o.dst: [c[i]] if prog.slots == 1 or pattern == "uniform" else
                    [c[i] if s % 2 == 0 else (o.lo + o.hi - c[i]) for s in range(prog.slots)] for i, o in enumerate(ins)}
            out, _ = concrete.run(prog, vals, exact=False)
            best = max(best, F(max(abs(v) for v in out[0])))
    return best


def main():
    res = {}
    for f in sorted(glob.glob(os.path.join(KDIR, "*.mlir.in")), key=lambda p: int(os.path.basename(p)[1:].split("_")[0])):
        k = os.path.basename(f)[:-8]
        res[k] = {}
        for n in NS:
            p = os.path.join(GEN, f"{k}_n{'dyn' if n == '?' else n}.mlir")
            open(p, "w").write(open(f).read().replace("@N@", n))
            prog = read(p)
            row = {}
            for m in SHOW:
                dom, strat = METHODS[m]
                t0 = time.perf_counter(); r = analyze(prog, dom, strat); dt = time.perf_counter() - t0
                row[m] = dict(q0=q0_bits(SCALE, r.B_out), B=None if r.B_out is None else (float(r.B_out) if r.B_out < 2**1000 else 'inf'),
                              status=r.status, evals=r.evals, ms=dt * 1e3,
                              mode=";".join(l.mode for l in r.loops))
            if n == "10":
                row["observed"] = float(observed_max(prog))
            res[k][n] = row
    # ---------------------------------------------------------------- print
    short = {"HEIR (as implemented)": "HEIR", "simple fix": "simple", "signed interval": "interval",
             "standard affine (unrolled)": "AA", "simple fix + invariant": "simple+inv",
             "interval + invariant": "intv+inv", "LoopRange": "LoopRange"}
    print("q0 bits from the OUTPUT bound (scale 45); n.e. = bound not established\n")
    print(f"{'kernel':18s} {'n':>5s} " + " ".join(f"{short[m]:>10s}" for m in SHOW) + "   observed max |out| (n=10)")
    for k, rows in res.items():
        for n, row in rows.items():
            cells = []
            for m in SHOW:
                c = row[m]
                cells.append(f"{'n.e.' if c['q0'] is None else c['q0']:>10}")
            extra = f"   {row['observed']:.4g} (needs {q0_bits(SCALE, F(row['observed'])) if row['observed'] > 0 else '-'})" if "observed" in row else ""
            print(f"{k:18s} {n:>5s} " + " ".join(cells) + extra)
    print("\nbody evaluations (n = 1000 | dynamic):")
    for k, rows in res.items():
        print(f"{k:18s} " + " ".join(f"{short[m]}={rows['1000'][m]['evals']}|{rows['?'][m]['evals']}" for m in SHOW))
    print("\nLoopRange modes (n = 10 | 1000 | dynamic):")
    for k, rows in res.items():
        print(f"{k:18s} " + " | ".join(rows[n]["LoopRange"]["mode"] for n in ("10", "1000", "?")))
    out = os.path.join(HERE, "..", "results", "e3_methods.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(res, open(out, "w"), indent=1); print("wrote", out)


if __name__ == "__main__":
    main()
