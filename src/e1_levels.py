"""e1_levels.py -- at which CKKS level, and under which modulus, does each E1 value live?

Reads, for every E1 program, the HEIR IR saved just before parameter generation
(runs/e1_<prog>_<OUT>/ir_before_param.txt, written by run_e1_obligation.py) and the primes
actually used (PARAMS line of runs/e1_<prog>_<OUT>/run.txt).  For every operation in the
encrypted body it records
    level    HEIR's mgmt level (0 = only q0 left, 1 = q0*q1, ...)
    deg      scale degree: the scale is Delta^deg (inputs and constants 1, a product adds
             the degrees, a modreduce/rescale subtracts 1)
    cap_log2 log2 of the largest |value| that level can hold: log2(Q_level / (2 Delta^deg)),
             Q_level = q0*...*q_level
No FHE is run; this only reads files.  Output: results/e1_levels.json.

    python3 e1_levels.py
"""
import json, math, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
RUNS = os.environ.get("W22_RUNS", os.path.join(ROOT, "runs"))
SCALE = 45
OP = re.compile(r"^\s*(%[\w]+) = ([\w.]+) (.*?)\{.*mgmt\.mgmt = #mgmt\.mgmt<level = (\d+)(?:, dimension = (\d+))?>")


def levels(run_dir):
    ir = open(os.path.join(run_dir, "ir_before_param.txt")).read()
    params = next(json.loads(l[7:]) for l in open(os.path.join(run_dir, "run.txt")) if l.startswith("PARAMS "))
    qb = params["Q_bits"]
    body = ir[ir.index("secret.generic("):]
    body = body[:body.index("} ->")]
    deg = {}
    ops = []
    for line in body.splitlines():
        if "^body(" in line:
            for a in re.findall(r"(%input\d+)", line): deg[a] = 1
            continue
        m = OP.match(line)
        if not m: continue
        dst, op, rest, lvl, dim = m.group(1), m.group(2), m.group(3), int(m.group(4)), m.group(5)
        args = [a for a in re.findall(r"%[\w]+", rest) if not a.startswith("%c")] or []
        d_in = [deg.get(a, 1) for a in args]          # mgmt.init constants are not in deg: scale 1 (matched)
        if op == "arith.mulf": d = sum(d_in)
        elif op == "mgmt.modreduce": d = max(d_in) - 1
        else: d = max(d_in) if d_in else 1
        deg[dst] = d
        cap = sum(qb[:lvl + 1]) - 1 - SCALE * d
        ops.append(dict(ssa=dst, op=op, level=lvl, deg=d, cap_log2=round(cap, 6)))
    out_level = int(re.search(r"func\.func @f\(.*?\) -> \(!secret[^{]*\{mgmt\.mgmt = #mgmt\.mgmt<level = (\d+)>", ir).group(1))
    return dict(Q_bits=qb, ops=ops, out_level=out_level, body_levels=sorted({o["level"] for o in ops}, reverse=True))


def main():
    e1 = json.load(open(os.path.join(ROOT, "results", "e1_obligation.json")))
    res = {}
    for r in e1["rows"]:
        name = r["program"][:-5]
        d = os.path.join(RUNS, f"e1_{name}_{r['q0_out']}")
        res[name] = levels(d)
        L = res[name]
        print(f"{name:12s} primes(bits)={[round(b, 2) for b in L['Q_bits']]}  body levels={L['body_levels']}  output level={L['out_level']}")
        for o in L["ops"]:
            if o["op"].startswith("arith.") or o["op"].startswith("tensor_ext") or o["op"].startswith("mgmt.modreduce"):
                print(f"    {o['ssa']:>5s} {o['op']:22s} level {o['level']}  scale Delta^{o['deg']}  holds |v| < 2^{o['cap_log2']:.3f}")
    p = os.path.join(ROOT, "results", "e1_levels.json")
    json.dump(res, open(p, "w"), indent=1)
    print("wrote", p)


if __name__ == "__main__":
    main()
