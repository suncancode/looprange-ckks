"""concrete.py -- exact reference semantics of an ir.Program (Fractions, no rounding).

run(prog, inputs) -> (returns, trace) where inputs maps every secret input to a list of S
values (or one value, broadcast), returns is the list of returned slot vectors, and trace
maps every SSA name to the largest |value| seen over all slots and all iterations.
Used (a) as the reference the decrypted CKKS output is compared with, and (b) by the
soundness fuzzer, which checks that every traced magnitude is below the computed bound.
"""
from __future__ import annotations
from fractions import Fraction as F
from typing import Dict, List

from ir import Op, Loop, Program


def run(prog: Program, inputs: Dict[str, List], n_dynamic: int = 0, exact: bool = True):
    S = prog.slots
    conv = (lambda v: F(v)) if exact else float
    env: Dict[str, list] = {}
    trace: Dict[str, F] = {}

    CAP = F(2) ** 1100

    def rec(name, vec):
        m = max(abs(v) for v in vec)
        if m > CAP: raise OverflowError("value exceeds 2^1100")
        if name not in trace or m > trace[name]: trace[name] = m

    def apply(op: Op, e, index):
        if op.kind == "input":
            v = inputs[op.dst]; v = list(v) if isinstance(v, (list, tuple)) else [v] * S
            v = [conv(x) for x in v]
            if len(v) == 1: v = v * S
            return v
        if op.kind == "const":
            vals = [conv(x) for x in op.values]
            return vals * S if len(vals) == 1 else vals
        a = e[op.args[0]]
        if op.kind == "add": b = e[op.args[1]]; return [x + y for x, y in zip(a, b)]
        if op.kind == "sub": b = e[op.args[1]]; return [x - y for x, y in zip(a, b)]
        if op.kind == "mul":
            b = e[op.args[1]]
            if exact and any(x.denominator.bit_length() + y.denominator.bit_length() > 60000 for x, y in zip(a, b)):
                raise OverflowError("exact reference too large")
            return [x * y for x, y in zip(a, b)]
        if op.kind == "neg": return [-x for x in a]
        if op.kind == "rot":
            coef, off = op.shift
            k = (coef * index + off) % S
            return [a[(s + k) % S] for s in range(S)]
        raise ValueError(op.kind)

    for it in prog.items:
        if isinstance(it, Op):
            env[it.dst] = apply(it, env, 0); rec(it.dst, env[it.dst]); continue
        n = it.n if it.n is not None else n_dynamic
        state = {h: env[init] for h, init in it.heads}
        for h in state: rec(h, state[h])
        for i in range(n):
            e = dict(env); e.update(state)
            for op in it.body:
                e[op.dst] = apply(op, e, i); rec(op.dst, e[op.dst])
            state = {h: e[y] for (h, _), y in zip(it.heads, it.yields)}
            for h in state: rec(h, state[h])
        for (h, _), r in zip(it.heads, it.results):
            env[r] = state[h]; rec(r, state[h])
    return [env[r] for r in prog.returns], trace
