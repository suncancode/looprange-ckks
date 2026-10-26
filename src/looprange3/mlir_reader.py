"""mlir_reader.py -- read the SAME .mlir file that HEIR compiles into the ir.Program.

Supported subset (anything else raises an error, so nothing is silently ignored):
  func.func @f(%x: f32 {secret.secret}, %v: tensor<Sxf32> {secret.secret}, ...) -> ...
  %c = arith.constant 0.5 : f32
  %c = arith.constant dense<0.5> : tensor<Sxf32>            (splat)
  %c = arith.constant dense<[0.1, 0.2, ...]> : tensor<Sxf32> (per-slot plaintext vector)
  %k = arith.constant 3 : index                               (rotation amounts)
  %y = arith.addf | arith.subf | arith.mulf %a, %b : T
  %y = arith.negf %a : T
  %y = tensor_ext.rotate %a, %k : tensor<Sxf32>, index        (%k constant, or the loop index)
  %r = affine.for %i = 0 to N iter_args(%h = %init, ...) -> (T, ...) { ... affine.yield ... }
       (several loops one after the other; N may be the token '?' for a dynamic trip count,
        which HEIR cannot compile but the analysis accepts)
  return %a, %r#1 : ...

Input ranges: every secret input lies in [-1, 1] slot-wise (HEIR's default input-range),
unless a comment  // range %x = [lo, hi]  appears in the file or ranges= is passed.
Constants are rounded to f32 first, because that f32 value is what HEIR encodes.
"""
from __future__ import annotations
import re, struct
from fractions import Fraction as F
from typing import Dict, List, Optional

from ir import Op, Loop, Program

V = r"%([A-Za-z0-9_]+)(?:#(\d+))?"


def f32(text: str) -> F:
    """The exact rational value of the f32 nearest to the decimal literal."""
    return F(struct.unpack("f", struct.pack("f", float(text)))[0])


def _ty_slots(ty: str) -> int:
    m = re.search(r"tensor<(\d+)x", ty)
    return int(m.group(1)) if m else 1


def read(path: str, ranges: Optional[Dict[str, tuple]] = None) -> Program:
    raw = open(path).read()
    ranges = dict(ranges or {})
    for name, lo, hi in re.findall(r"//\s*range\s+%(\w+)\s*=\s*\[\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\]", raw):
        ranges.setdefault(name, (F(lo), F(hi)))
    text = "\n".join(l.split("//")[0] for l in raw.splitlines())
    m = re.search(r"func\.func\s+@(\w+)\((.*?)\)\s*->", text, re.S)
    if not m: raise ValueError("no func.func")
    items: List = []
    slots = 1
    for name, ty in re.findall(r"%(\w+)\s*:\s*([^{,]+?)\s*\{secret\.secret\}", m.group(2)):
        slots = max(slots, _ty_slots(ty))
        lo, hi = ranges.get(name, (F(-1), F(1)))
        items.append(Op("input", name, lo=F(lo), hi=F(hi)))
    if not items: raise ValueError("no secret inputs")

    index_consts: Dict[str, int] = {}
    returns: List[str] = []
    loop: Optional[Loop] = None
    cur = items
    alias: Dict[str, str] = {}

    def nm(name, idx=None):
        n = name if idx is None else f"{name}#{idx}"
        return alias.get(n, n)

    body = text[text.index("{", m.end()) + 1:]
    for line in body.splitlines():
        s = line.strip()
        if not s or s in ("{", "}") or s.startswith(") ->") or s.startswith("->"): continue
        if (mm := re.match(V + r"\s*=\s*arith\.constant\s+(-?\d+)\s*:\s*index", s)):
            index_consts[mm.group(1)] = int(mm.group(3)); continue
        if (mm := re.match(V + r"\s*=\s*arith\.constant\s+dense<\[(.*?)\]>\s*:\s*(\S+)", s)):
            vals = [f32(v) for v in mm.group(3).split(",")]
            slots = max(slots, len(vals))
            cur.append(Op("const", mm.group(1), values=vals)); continue
        if (mm := re.match(V + r"\s*=\s*arith\.constant\s+dense<([-+0-9.eE]+)>\s*:\s*(\S+)", s)):
            cur.append(Op("const", mm.group(1), values=[f32(mm.group(3))])); continue
        if (mm := re.match(V + r"\s*=\s*arith\.constant\s+([-+0-9.eE]+)\s*:\s*f32", s)):
            cur.append(Op("const", mm.group(1), values=[f32(mm.group(3))])); continue
        if (mm := re.match(r"%(\w+)(?::(\d+))?\s*=\s*affine\.for\s+%(\w+)\s*=\s*0\s+to\s+(\d+|\?)\s+iter_args\((.*?)\)", s)):
            if loop is not None: raise ValueError("nested loops are not supported")
            res, nres, idx, n, args = mm.groups()
            heads = [(h, nm(*init)) for h, init in
                     [(a, (b, c or None)) for a, b, c in re.findall(r"%(\w+)\s*=\s*" + V, args)]]
            heads = [(h, init) for h, init in heads]
            k = int(nres or 1)
            results = [f"{res}#{j}" if nres else res for j in range(k)]
            loop = Loop(None if n == "?" else int(n), heads, [], [], results, index=idx)
            cur = loop.body; continue
        if (mm := re.match(r"affine\.yield\s+(.*?)\s*:", s)):
            loop.yields = [nm(a, b or None) for a, b in re.findall(V, mm.group(1))]
            items.append(loop); loop = None; cur = items; continue
        if (mm := re.match(r"return\s+(.*?)\s*:", s)):
            returns = [nm(a, b or None) for a, b in re.findall(V, mm.group(1))]; continue
        if (mm := re.match(V + r"\s*=\s*arith\.(addf|subf|mulf)\s+" + V + r"\s*,\s*" + V, s)):
            d, _, op, a, ai, b, bi = mm.groups()
            cur.append(Op({"addf": "add", "subf": "sub", "mulf": "mul"}[op], d,
                          (nm(a, ai or None), nm(b, bi or None)))); continue
        if (mm := re.match(V + r"\s*=\s*arith\.negf\s+" + V, s)):
            d, _, a, ai = mm.groups()
            cur.append(Op("neg", d, (nm(a, ai or None),))); continue
        if (mm := re.match(V + r"\s*=\s*tensor_ext\.rotate\s+" + V + r"\s*,\s*%(\w+)", s)):
            d, _, a, ai, k = mm.groups()
            if k in index_consts: shift = (0, index_consts[k])
            elif loop is not None and k == loop.index: shift = (1, 0)
            else: raise ValueError(f"rotation amount %{k} must be a constant or the loop index")
            cur.append(Op("rot", d, (nm(a, ai or None),), shift=shift)); continue
        if s.startswith("func.func") or s.startswith("module"): continue
        raise ValueError(f"unsupported line: {s}")
    if not returns: raise ValueError("no return")
    return Program(path.rsplit("/", 1)[-1], slots, items, returns)
