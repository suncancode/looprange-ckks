"""cli.py -- run every method on one .mlir file and print bounds and q0 bits.

  python3 cli.py prog.mlir [--scale 45] [--json] [--range x=-1:1] [--methods LoopRange,...]

Output lines that scripts parse:
  Q0 <method-key> OUT=<bits|NA> ALL=<bits|NA> STATUS=<status>
where <method-key> is: heir-impl simple-fix interval affine-unroll looprange ...
"""
from __future__ import annotations
import json, os, sys
from fractions import Fraction as F
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mlir_reader import read
from analysis import analyze, q0_bits, METHODS

KEYS = {"HEIR (as implemented)": "heir-impl", "simple fix": "simple-fix",
        "signed interval": "interval", "standard affine (unrolled)": "affine-unroll",
        "simple fix + invariant": "simple-fix-inv", "interval + invariant": "interval-inv", "affine + invariant only": "affine-inv",
        "LoopRange": "looprange"}


def fmt(B):
    return "not established" if B is None else f"{float(B):.6g}"


def main(argv):
    path = argv[0]
    scale = int(argv[argv.index("--scale") + 1]) if "--scale" in argv else 45
    ranges = {}
    if "--range" in argv:
        for spec in argv[argv.index("--range") + 1].split(","):
            n, r = spec.split("="); lo, hi = r.split(":"); ranges[n] = (F(lo), F(hi))
    names = list(METHODS)
    if "--methods" in argv:
        want = argv[argv.index("--methods") + 1].split(",")
        names = [m for m in names if KEYS[m] in want]
    prog = read(path, ranges)
    out = {}
    print(f"program  {path}   slots={prog.slots}   loops={[l.n for l in prog.loops()]}")
    for name in names:
        dom, strat = METHODS[name]
        r = analyze(prog, dom, strat)
        modes = ";".join(f"{li.mode}" for li in r.loops) or "straight-line"
        qo, qa = q0_bits(scale, r.B_out), q0_bits(scale, r.B_all)
        out[KEYS[name]] = dict(status=r.status, B_out=None if r.B_out is None else float(r.B_out),
                               B_all=None if r.B_all is None else float(r.B_all),
                               q0_out=qo, q0_all=qa, mode=modes, evals=r.evals, seconds=r.seconds)
        print(f"  {name:28s} OUT={fmt(r.B_out):>12s} ALL={fmt(r.B_all):>12s}  "
              f"q0(OUT)={qo if qo else 'NA':>3}  q0(ALL)={qa if qa else 'NA':>3}  "
              f"[{modes}; {r.evals} body evals; {r.seconds*1e3:.1f} ms]")
    for k, v in out.items():
        print(f"Q0 {k} OUT={v['q0_out'] or 'NA'} ALL={v['q0_all'] or 'NA'} STATUS={v['status']}")
    if "--json" in argv:
        print("JSON " + json.dumps(out))
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
