"""fuzz.py -- soundness check by random testing (complements the proof, does not replace it).

Random programs over S-slot vectors (S in {1, 4, 8}): inputs in random boxes, scalar and
per-slot constants, add/sub/mul/neg/rot, one or two sequential loops with 1-2 carried
values, static or dynamic trip count.  Each program is run EXACTLY (Fractions) on the box
corners plus random points; for a dynamic loop every n in 0..N_DYN is run.  A violation is
any SSA value whose observed |value| exceeds the bound the method reports for it.
Usage: python3 fuzz.py [count] [seed]
"""
import random, sys, time, json
from fractions import Fraction as F
from ir import Op, Loop, Program
from analysis import analyze, METHODS
import concrete

N_DYN = 24

def rnd_const(R, S):
    if S > 1 and R.random() < 0.3:
        return [F(R.choice([-2, -1, -0.5, -0.25, 0.25, 0.5, 0.75, 1, 1.5])) for _ in range(S)]
    return [F(R.choice([-2, -1.5, -1, -0.75, -0.5, -0.25, 0.25, 0.5, 0.75, 0.9, 1, 1.25, 2, 3, 8]))]

def rnd_program(R, idx):
    S = R.choice([1, 1, 4, 8])
    items, names = [], []
    for j in range(R.choice([1, 2])):
        lo = F(R.choice([-2, -1, -1, 0, 0.5])); hi = lo + F(R.choice([0.5, 1, 2, 3]))
        items.append(Op("input", f"x{j}", lo=lo, hi=hi)); names.append(f"x{j}")
    cnt = [0]
    def new(): cnt[0] += 1; return f"v{cnt[0]}"
    def ops_block(avail, k, in_loop, index):
        out = []
        for _ in range(k):
            r = R.random()
            if r < 0.15:
                d = new(); out.append(Op("const", d, values=rnd_const(R, S))); avail.append(d); continue
            kind = R.choice(["add", "sub", "sub", "mul", "neg", "rot"] if S > 1 else ["add", "sub", "sub", "mul", "neg"])
            a = R.choice(avail); d = new()
            if kind in ("add", "sub", "mul"):
                b = R.choice(avail); out.append(Op(kind, d, (a, b)))
            elif kind == "neg": out.append(Op("neg", d, (a,)))
            else:
                sh = (1, R.randrange(S)) if (in_loop and R.random() < 0.3) else (0, R.randrange(1, S))
                out.append(Op("rot", d, (a,), shift=sh))
            avail.append(d)
        return out
    avail = list(names)
    items += ops_block(avail, R.randrange(0, 3), False, None)
    for L in range(R.choice([1, 1, 2])):
        nh = R.choice([1, 1, 2])
        heads = [(f"h{L}_{i}", R.choice(avail)) for i in range(nh)]
        bav = avail + [h for h, _ in heads]
        body = ops_block(bav, R.randrange(2, 6), True, "i")
        # contractive-ish update with prob 0.5 so that invariants exist sometimes
        yields = []
        for h, _ in heads:
            if R.random() < 0.5:
                a = R.choice(bav); d1, d2, d3 = new(), new(), new()
                al = F(R.choice([0.125, 0.25, 0.5]))
                body += [Op("sub", d1, (a, h)), Op("const", d2, values=[al]), Op("mul", d3, (d1, d2))]
                d4 = new(); body.append(Op("add", d4, (h, d3))); yields.append(d4)
            else:
                yields.append(body[-1].dst if body else h)
        n = None if R.random() < 0.3 else R.randrange(1, 13)
        res = [f"r{L}_{i}" for i in range(nh)]
        items.append(Loop(n, heads, body, yields, res, index="i"))
        avail += res
    items += ops_block(avail, R.randrange(0, 3), False, None)
    rets = [avail[-1]]
    return Program(f"fuzz{idx}", S, items, rets)

def corners(prog, R, k=6):
    ins = prog.inputs(); pts = []
    import itertools
    for c in itertools.product(*[(o.lo, o.hi) for o in ins]):
        pts.append({o.dst: [c[i]] for i, o in enumerate(ins)})
    for _ in range(k):
        pts.append({o.dst: [o.lo + (o.hi - o.lo) * F(R.randrange(0, 17), 16) for _ in range(prog.slots)] for o in ins})
    return pts

def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    R = random.Random(seed)
    stats = {m: dict(viol=0, bounded=0, not_est=0) for m in METHODS}
    examples = {}
    t0 = time.time(); done = 0
    for idx in range(count):
        prog = rnd_program(R, idx)
        dyn = any(l.n is None for l in prog.loops())
        traces = []
        for pt in corners(prog, R):
            for nd in (range(N_DYN + 1) if dyn else [0]):
                try:
                    _, tr = concrete.run(prog, pt, n_dynamic=nd)
                except OverflowError:
                    continue
                traces.append(tr)
        for m, (dom, strat) in METHODS.items():
            try:
                r = analyze(prog, dom, strat)
            except Exception as ex:
                print("ANALYSIS ERROR", m, prog.name, repr(ex)); raise
            if r.status != "bounded":
                stats[m]["not_est"] += 1; continue
            stats[m]["bounded"] += 1
            bad = None
            for tr in traces:
                for v, mag in tr.items():
                    if v in r.per_value and mag > r.per_value[v]:
                        bad = (v, float(mag), float(r.per_value[v])); break
                if bad: break
            if bad:
                stats[m]["viol"] += 1; examples.setdefault(m, (prog.name, bad))
        done += 1
    print(f"{done} random programs, seed {seed}, {time.time() - t0:.1f} s")
    print(f"{'method':30s} {'bounded':>8s} {'not established':>16s} {'programs with a violated bound':>32s}")
    for m, s in stats.items():
        print(f"{m:30s} {s['bounded']:8d} {s['not_est']:16d} {s['viol']:32d}")
    for m, ex in examples.items(): print("  first violation", m, ex)
    out = dict(count=done, seed=seed, stats=stats, first_violation={m: [e[0], list(e[1])] for m, e in examples.items()})
    print("JSON " + json.dumps(out))
    import os
    rd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results")
    os.makedirs(rd, exist_ok=True)
    json.dump(out, open(os.path.join(rd, "e4_fuzz.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
