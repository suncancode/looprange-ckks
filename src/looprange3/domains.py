"""domains.py -- abstract domains for value bounds.  Everything is exact (fractions.Fraction),
so every inequality the analysis checks is a proof, not a floating-point comparison.

Four domains, from coarsest to finest:

  HeirImpl  one number B >= |v| per value, with HEIR's rules AS IMPLEMENTED
            (RangeAnalysis.cpp @ e4497fb): add = Ba + Bb, mul = Ba * Bb, constant = max|c|,
            and every other op (subf, negf, rotate, ...) copies the bound of its FIRST
            operand.  Unsound for subtraction; included only to reproduce HEIR.
  Mag       the "simple fix": HEIR's rules with sub = Ba + Bb (and neg, rot = Ba).
  Interval  signed interval [lo, hi] (Moore).  The same interval holds for every slot.
  AA        affine form  c + sum_i a_i e_i + [-r, r]  (Stolfi & de Figueiredo), e_i in [-1, 1].
            The same form describes every slot s, with the noise symbols taking slot-dependent
            values e_i(s).  A symbol is a pair (base, shift): (b, k) denotes the function
            s -> e_b((s + k) mod S), so a rotation by j maps (b, k) to (b, k + j) EXACTLY.
            When the shift is not known (rotation by the loop index inside an invariant
            check) the value is de-correlated: one fresh symbol of radius rad(v).

Each domain offers: input(lo, hi), const(values), add, sub, mul, neg, rot(v, shift|None),
mag(v) (an upper bound on max_s |v(s)|), box(v) = (lo, hi), from_box(lo, hi),
contains(outer_box, v).
"""
from __future__ import annotations
import itertools
from fractions import Fraction
from typing import Dict, Optional, Tuple

F = Fraction
ZERO = F(0)


def fmax_abs(lo: F, hi: F) -> F:
    return max(abs(lo), abs(hi))


MAX_BITS = 160


def up(v: F) -> F:
    """v itself, or (if its denominator is huge) the nearest float64 value >= v."""
    if v.denominator.bit_length() <= MAX_BITS: return v
    return _round_up(v)


def down(v: F) -> F:
    if v.denominator.bit_length() <= MAX_BITS: return v
    return -_round_up(-v)


# --------------------------------------------------------------------------- HEIR as implemented
class HeirImpl:
    name = "heir-impl"
    def input(self, lo, hi): return fmax_abs(lo, hi)
    def const(self, values): return max(abs(v) for v in values)
    def add(self, a, b): return up(a + b)
    def sub(self, a, b): return a              # .Default: first operand
    def mul(self, a, b): return up(a * b)
    def neg(self, a): return a                 # .Default
    def rot(self, a, shift): return a          # .Default ("Rotation does not change the CKKS range")
    def mag(self, a): return a
    def box(self, a): return (-a, a)
    def from_box(self, lo, hi): return fmax_abs(lo, hi)
    def contains(self, S, a): return a <= fmax_abs(*S)


# --------------------------------------------------------------------------- simple fix
class Mag(HeirImpl):
    name = "simple-fix"
    def sub(self, a, b): return up(a + b)      # |a - b| <= |a| + |b|


# --------------------------------------------------------------------------- signed intervals
class Interval:
    name = "interval"
    def input(self, lo, hi): return (lo, hi)
    def const(self, values): return (min(values), max(values))
    def add(self, a, b): return (down(a[0] + b[0]), up(a[1] + b[1]))
    def sub(self, a, b): return (down(a[0] - b[1]), up(a[1] - b[0]))
    def mul(self, a, b):
        p = [a[0] * b[0], a[0] * b[1], a[1] * b[0], a[1] * b[1]]
        return (down(min(p)), up(max(p)))
    def neg(self, a): return (-a[1], -a[0])
    def rot(self, a, shift): return a          # every slot of the input lies in a
    def mag(self, a): return fmax_abs(*a)
    def box(self, a): return a
    def from_box(self, lo, hi): return (lo, hi)
    def contains(self, S, a): return S[0] <= a[0] and a[1] <= S[1]


# --------------------------------------------------------------------------- affine arithmetic
class Form:
    __slots__ = ("c", "a", "r")
    def __init__(self, c: F, a: Dict[Tuple[int, int], F], r: F):
        self.c, self.a, self.r = c, a, r
    def rad(self) -> F: return sum((abs(v) for v in self.a.values()), ZERO) + self.r
    def __repr__(self):
        return f"Form(c={float(self.c):.6g}, syms={len(self.a)}, rad={float(self.rad()):.6g})"


class AA:
    name = "affine"
    MAX_DEN_BITS = 4096         # snap coefficients whose denominators grow beyond this

    def __init__(self, slots: int, max_syms: int = 256):
        self.S = max(1, slots)
        self.max_syms = max_syms
        self._next = itertools.count(1)

    # -- helpers --------------------------------------------------------------
    def fresh(self) -> Tuple[int, int]:
        return (next(self._next), 0)

    def _tidy(self, f: Form) -> Form:
        """Normalise a form without losing soundness (Stolfi & de Figueiredo 2003, Sec. 3.3):
        every approximation error becomes a FRESH noise symbol, never an unstructured residual,
        because a symbol keeps being tracked exactly by later linear operations (a contracting
        loop then also contracts the error).
          (1) a coefficient or centre whose denominator exceeds MAX_DEN_BITS is rounded to a
              multiple of 2^-128; the total rounding error goes into one fresh symbol;
          (2) a residual r > 0 (e.g. the quadratic term of a product) becomes a fresh symbol;
          (3) beyond max_syms symbols, the smallest ones are merged into one fresh symbol
              whose coefficient is the sum of their absolute values."""
        K = 1 << 128
        a, err = {}, f.r
        for k, v in f.a.items():
            if v == 0: continue
            if v.denominator.bit_length() > self.MAX_DEN_BITS:
                w = F(round(v * K), K); err += abs(v - w); v = w
                if v == 0: continue
            a[k] = v
        c = f.c
        if c.denominator.bit_length() > self.MAX_DEN_BITS:
            w = F(round(c * K), K); err += abs(c - w); c = w
        if err:
            a[self.fresh()] = err if err.denominator.bit_length() <= self.MAX_DEN_BITS else _round_up(err)
        if len(a) > self.max_syms:
            keep = sorted(a.items(), key=lambda kv: -abs(kv[1]))
            merged = sum((abs(v) for _, v in keep[self.max_syms - 1:]), ZERO)
            a = dict(keep[:self.max_syms - 1])
            a[self.fresh()] = merged
        return Form(c, a, ZERO)

    # -- transfer functions -----------------------------------------------------
    def input(self, lo: F, hi: F) -> Form:
        c, h = (lo + hi) / 2, (hi - lo) / 2
        return Form(c, {self.fresh(): h} if h else {}, ZERO)

    def const(self, values) -> Form:
        lo, hi = min(values), max(values)
        if lo == hi:
            return Form(lo, {}, ZERO)
        # a known plaintext vector: c_s = mid + rad * eta(s), eta(s) = (c_s - mid)/rad in [-1, 1]
        return Form((lo + hi) / 2, {self.fresh(): (hi - lo) / 2}, ZERO)

    def add(self, x: Form, y: Form) -> Form:
        a = dict(x.a)
        for k, v in y.a.items(): a[k] = a.get(k, ZERO) + v
        return self._tidy(Form(x.c + y.c, a, x.r + y.r))

    def neg(self, x: Form) -> Form:
        return Form(-x.c, {k: -v for k, v in x.a.items()}, x.r)

    def sub(self, x: Form, y: Form) -> Form:
        return self.add(x, self.neg(y))

    def mul(self, x: Form, y: Form) -> Form:
        # (cx + Lx + dx)(cy + Ly + dy) = cx cy + cy Lx + cx Ly + [cx dy + cy dx + (Lx+dx)(Ly+dy)]
        a = {k: y.c * v for k, v in x.a.items()}
        for k, v in y.a.items(): a[k] = a.get(k, ZERO) + x.c * v
        r = abs(x.c) * y.r + abs(y.c) * x.r + x.rad() * y.rad()
        return self._tidy(Form(x.c * y.c, a, r))

    def rot(self, x: Form, shift: Optional[int]) -> Form:
        if not x.a and x.r == 0:
            return x                                   # a uniform constant: rotation-invariant
        if shift is None:                              # unknown shift: de-correlate (Lemma L3)
            return Form(x.c, {self.fresh(): x.rad()}, ZERO)
        s = shift % self.S
        a = {(b, (k + s) % self.S): v for (b, k), v in x.a.items()}
        return Form(x.c, a, x.r)                      # residual: |d(s+j)| <= r as well

    # -- queries ------------------------------------------------------------------
    def mag(self, x: Form) -> F: return abs(x.c) + x.rad()
    def box(self, x: Form): rr = x.rad(); return (x.c - rr, x.c + rr)
    def from_box(self, lo, hi) -> Form: return self.input(lo, hi)
    def contains(self, S, x: Form) -> bool:
        lo, hi = self.box(x); return S[0] <= lo and hi <= S[1]


def _round_up(r: F) -> F:
    """The smallest multiple of 2^-128 that is >= r (exact; sound outward rounding)."""
    K = 1 << 128
    n = -((-r.numerator * K) // r.denominator)     # ceil(r * K)
    return F(n, K)


DOMAINS = {"heir-impl": HeirImpl, "simple-fix": Mag, "interval": Interval, "affine": AA}
