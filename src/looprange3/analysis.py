"""analysis.py -- the loop engine and the obligations.

analyze(program, domain, strategy) returns, for one abstract domain and one loop strategy:

  status     "bounded"          every requested bound was established
             "not-established"  some loop has a dynamic trip count and no inductive box was
                                found within the search limits (this is NOT a claim that
                                the loop is unbounded)
  B_out      bound on the returned values               (obligation OUT)
  B_all      bound on every SSA value, every iteration  (obligation ALL)
  per_value  bound per SSA name (max over iterations)
  loops      per loop: mode ("iterate" | "invariant@k" | "invariant(widened)@k" |
             "not-established"), body evaluations, the invariant box if any

Strategies
  "unroll"     evaluate the body exactly n times (what HEIR does after unrolling, and what
               standard interval / affine analyses do on the unrolled program).  A dynamic
               trip count cannot be unrolled -> not established.
  "invariant"  LoopRange's engine: evaluate forward; at k = 1, 2, 4, 8, ... try to prove a
               box S inductive (T(S) subset of S); from k >= 8 (or for a dynamic n) also run
               power-of-two Kleene widening.  The engine is the same for every domain, so the
               comparison separates the domain (precision) from the loop strategy (cost and
               dynamic n).

Stopping rule (always terminates):
  static n : at most n forward evaluations, plus at most C = (#checkpoints <= floor(log2 n)+1)
             x (2 candidates + W widening rounds) x (cells per check) invariant evaluations;
  dynamic n: the same with n replaced by K_max (default 64).
  After that the result is "not-established" (dynamic n) -- never "unbounded".
"""
from __future__ import annotations
import math, time
from dataclasses import dataclass, field
from fractions import Fraction as F
from typing import Dict, List, Optional, Tuple

from ir import Op, Loop, Program
from domains import AA, DOMAINS


@dataclass
class LoopInfo:
    mode: str
    evals: int
    invariant: Optional[Dict[str, Tuple[F, F]]] = None


@dataclass
class Result:
    domain: str
    strategy: str
    status: str
    B_out: Optional[F]
    B_all: Optional[F]
    per_value: Dict[str, F]
    loops: List[LoopInfo]
    seconds: float
    evals: int = 0

    def bits(self, which: str = "out") -> Optional[int]:
        B = self.B_out if which == "out" else self.B_all
        return None if B is None else ceil_log2(B)


def ceil_log2(B: F) -> int:
    """Smallest integer k (possibly negative) with 2^k >= B, for B > 0 (exact)."""
    if B <= 0: raise ValueError("bound must be positive")
    k = B.numerator.bit_length() - B.denominator.bit_length()
    while F(2) ** k < B: k += 1
    while F(2) ** (k - 1) >= B: k -= 1
    return k


def q0_bits(scale_bits: int, B: Optional[F]) -> Optional[int]:
    """HEIR's rule (GenerateParamCKKS.cpp l.97-98): scale + ceil(log2 B) + 2.  Like HEIR, no
    clipping at 0: B = 0.5 gives scale + 1.  B = 0 (an identically zero output) gives scale + 2."""
    if B is None: return None
    return scale_bits + (ceil_log2(B) if B > 0 else 0) + 2


def p2(v: F, outward: int) -> F:
    """Move v outward (outward=-1 for a lower end, +1 for an upper end) to 0 or a signed
    power of two.  Free at bit granularity: ceil(log2 |v|) does not change."""
    if v == 0: return v
    up = F(2) ** ceil_log2(abs(v))          # smallest power of two >= |v|
    down = up if up == abs(v) else up / 2   # largest power of two <= |v|
    if outward > 0: return up if v > 0 else -down
    return -up if v < 0 else down


BUDGET_BITS = 1024                 # a bound above 2^1024 is useless for CKKS; stop computing it
BUDGET = F(2) ** BUDGET_BITS


class Engine:
    def __init__(self, prog: Program, domain: str, strategy: str = "invariant",
                 k_max: int = 64, widen_rounds: int = 12, subdivide: bool = True):
        self.prog, self.strategy = prog, strategy
        self.D = AA(prog.slots) if domain == "affine" else DOMAINS[domain]()
        self.k_max, self.W, self.subdivide = k_max, widen_rounds, subdivide
        self.maxes: Dict[str, F] = {}
        self.evals = 0

    # -- one operation ------------------------------------------------------------
    def apply(self, op: Op, env, index: Optional[int]):
        D = self.D
        if op.kind == "input": return D.input(op.lo, op.hi)
        if op.kind == "const": return D.const(op.values)
        a = env[op.args[0]]
        if op.kind == "add": return D.add(a, env[op.args[1]])
        if op.kind == "sub": return D.sub(a, env[op.args[1]])
        if op.kind == "mul": return D.mul(a, env[op.args[1]])
        if op.kind == "neg": return D.neg(a)
        if op.kind == "rot":
            coef, off = op.shift
            shift = off if coef == 0 else (None if index is None else coef * index + off)
            return D.rot(a, shift)
        raise ValueError(op.kind)

    def record(self, name, v):
        m = self.D.mag(v)
        if name not in self.maxes or m > self.maxes[name]: self.maxes[name] = m

    def run_body(self, loop: Loop, state, env, index, record=True):
        e = dict(env); e.update(state)
        for op in loop.body:
            e[op.dst] = self.apply(op, e, index)
            if record: self.record(op.dst, e[op.dst])
        self.evals += 1
        return e

    # -- invariant check ------------------------------------------------------------
    def check(self, loop: Loop, S, env):
        """Exact test T(S) subset of S.  Returns (ok, [body environments evaluated on S])."""
        D = self.D
        st = {h: D.from_box(*S[h]) for h, _ in loop.heads}
        e = self.run_body(loop, st, env, None, record=False)
        if all(D.contains(S[h], e[y]) for (h, _), y in zip(loop.heads, loop.yields)):
            return True, [e]
        # subdivision (affine only, slot-wise bodies only): cover S by cells, test every cell
        if not (self.subdivide and isinstance(D, AA)) or any(o.kind == "rot" for o in loop.body):
            return False, []
        heads = [h for h, _ in loop.heads]
        for m in (4, 16):
            if m ** len(heads) > 1024: break
            grids = []
            for h in heads:
                lo, hi = S[h]
                grids.append([(lo + (hi - lo) * i / m, lo + (hi - lo) * (i + 1) / m) for i in range(m)]
                             if hi > lo else [(lo, hi)])
            envs, good = [], True
            for combo in itertools_product(*grids):
                st = {h: D.from_box(*c) for h, c in zip(heads, combo)}
                e = self.run_body(loop, st, env, None, record=False)
                if not all(D.contains(S[h], e[y]) for (h, _), y in zip(loop.heads, loop.yields)):
                    good = False; break
                envs.append(e)
            if good: return True, envs
        return False, []

    def image_box(self, loop, S, env):
        D = self.D
        st = {h: D.from_box(*S[h]) for h, _ in loop.heads}
        e = self.run_body(loop, st, env, None, record=False)
        return {h: D.box(e[y]) for (h, _), y in zip(loop.heads, loop.yields)}

    # -- one loop -------------------------------------------------------------------------
    def run_loop(self, loop: Loop, env) -> Tuple[Dict[str, object], LoopInfo]:
        D = self.D
        state = {h: env[init] for h, init in loop.heads}
        hull = {h: D.box(state[h]) for h in state}
        start = self.evals
        if loop.n is None and self.strategy == "unroll":
            return None, LoopInfo("not-established (dynamic n cannot be unrolled)", 0)
        limit = loop.n if loop.n is not None else self.k_max
        next_check = 1
        for k in range(1, limit + 1):
            e = self.run_body(loop, state, env, k - 1)
            state = {h: e[y] for (h, _), y in zip(loop.heads, loop.yields)}
            if any(D.mag(v) > BUDGET for v in state.values()):
                return None, LoopInfo(f"not-established (bound exceeds 2^{BUDGET_BITS} at k={k})",
                                      self.evals - start)
            for h in state:
                self.record(h, state[h])
                lo, hi = D.box(state[h]); hl, hh = hull[h]
                hull[h] = (min(lo, hl), max(hi, hh))
            if loop.n is not None and k == loop.n:
                return state, LoopInfo("iterate", self.evals - start)
            if self.strategy == "invariant" and k == next_check:
                next_check *= 2
                cands = [dict(hull), {h: (p2(lo, -1), p2(hi, +1)) for h, (lo, hi) in hull.items()}]
                for S in cands:
                    ok, envs = self.check(loop, S, env)
                    if ok:
                        return self._accept(loop, S, envs, f"invariant@{k}", start)
                if loop.n is None or k >= 8:
                    S = cands[1]
                    for _ in range(self.W):
                        if any(abs(v) > F(2) ** 200 for b in S.values() for v in b): break
                        ok, envs = self.check(loop, S, env)
                        if ok:
                            return self._accept(loop, S, envs, f"invariant(widened)@{k}", start)
                        img = self.image_box(loop, S, env)
                        S = {h: (p2(min(S[h][0], img[h][0]), -1), p2(max(S[h][1], img[h][1]), +1)) for h in S}
        return None, LoopInfo("not-established (no inductive box within the search limits)",
                              self.evals - start)

    def _accept(self, loop, S, envs, mode, start):
        D = self.D
        for e in envs:                                   # every later iteration is covered
            for op in loop.body:
                self.record(op.dst, e[op.dst])
        for h, _ in loop.heads:                          # carried values lie in S
            m = max(abs(S[h][0]), abs(S[h][1]))
            if h not in self.maxes or m > self.maxes[h]: self.maxes[h] = m
        state = {h: D.from_box(*S[h]) for h, _ in loop.heads}
        return state, LoopInfo(mode, self.evals - start, invariant=dict(S))

    # -- whole program ---------------------------------------------------------------------
    def run(self) -> Result:
        t0 = time.perf_counter()
        env, infos, ok = {}, [], True
        for it in self.prog.items:
            if isinstance(it, Op):
                env[it.dst] = self.apply(it, env, None); self.record(it.dst, env[it.dst])
                continue
            for h, init in it.heads:
                self.record(h, env[init])
            final, info = self.run_loop(it, env)
            infos.append(info)
            if final is None:
                ok = False; break
            for (h, _), r in zip(it.heads, it.results):
                env[r] = final[h]; self.record(r, final[h])
        dt = time.perf_counter() - t0
        if not ok:
            return Result(self.D.name, self.strategy, "not-established", None, None,
                          dict(self.maxes), infos, dt, self.evals)
        B_out = max(self.D.mag(env[r]) for r in self.prog.returns)
        B_all = max(self.maxes.values())
        return Result(self.D.name, self.strategy, "bounded", B_out, B_all, dict(self.maxes),
                      infos, dt, self.evals)


def itertools_product(*xs):
    import itertools
    return itertools.product(*xs)


def analyze(prog: Program, domain: str = "affine", strategy: str = "invariant", **kw) -> Result:
    if strategy == "looprange":
        return looprange(prog, **kw)
    return Engine(prog, domain, strategy, **kw).run()


def looprange(prog: Program, forward_cap: int = 4096, **kw) -> Result:
    """LoopRange = affine forms + the invariant engine.  When every trip count is static and
    the total number of iterations is at most forward_cap, the forward (unrolled) affine
    bound is computed as well and each value gets the smaller of the two bounds (both are
    sound, so their minimum is sound).  The invariant part is what makes a bound valid for
    every iteration of a rolled loop and for a dynamic trip count."""
    inv = Engine(prog, "affine", "invariant", **kw).run()
    ns = [l.n for l in prog.loops()]
    fwd = None
    if all(n is not None for n in ns) and sum(ns) <= forward_cap:
        fwd = Engine(prog, "affine", "unroll", **kw).run()
    if fwd is None or fwd.status != "bounded":
        inv.strategy = "looprange"; return inv
    if inv.status != "bounded":
        fwd.strategy = "looprange"; return fwd
    per = {k: min(v, fwd.per_value.get(k, v)) for k, v in inv.per_value.items()}
    loops = [LoopInfo(a.mode + " (+forward)", a.evals + b.evals, a.invariant) for a, b in zip(inv.loops, fwd.loops)]
    return Result("affine", "looprange", "bounded", min(inv.B_out, fwd.B_out), max(per.values()), per, loops,
                  inv.seconds + fwd.seconds, inv.evals + fwd.evals)


METHODS = {
    # name in the report            domain        loop strategy
    "HEIR (as implemented)":        ("heir-impl",  "unroll"),
    "simple fix":                   ("simple-fix", "unroll"),
    "signed interval":              ("interval",   "unroll"),
    "standard affine (unrolled)":   ("affine",     "unroll"),
    "simple fix + invariant":       ("simple-fix", "invariant"),
    "interval + invariant":         ("interval",   "invariant"),
    "affine + invariant only":      ("affine",     "invariant"),
    "LoopRange":                    ("affine",     "looprange"),
}
