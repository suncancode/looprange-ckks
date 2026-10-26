"""ir.py -- the small program representation shared by the reader, the analyses and the
exact reference interpreter.

A program works on slot vectors of a fixed length S (a scalar f32 program has S = 1).
Values are SSA names.  Operations (all slot-wise except rotation):

    input   dst                      a secret input; every slot lies in [lo, hi]
    const   dst  values              a plaintext constant: one value (broadcast) or S values
    add     dst  a b                 a + b
    sub     dst  a b                 a - b
    mul     dst  a b                 a * b      (ciphertext x ciphertext or x plaintext)
    neg     dst  a                   -a
    rot     dst  a  shift            slot s of the result is slot (s + shift) mod S of a;
                                     shift = (coef * i + offset) for the loop index i
                                     (coef = 0 for a constant shift)

A Loop runs its body n times (n = None: public but dynamic trip count).  iter_args are
(head, init) pairs; the body yields one value per head; the loop's results are the
final values of the heads.  Loops are sequential (no nesting), as in the HEIR inputs we use.

All constants are kept as exact rationals (fractions.Fraction).  An f32 literal in MLIR is
first rounded to the nearest f32 and that f32 is the exact constant (this is what HEIR
encodes); see mlir_reader.f32().
"""
from __future__ import annotations
from dataclasses import dataclass, field
from fractions import Fraction
from typing import List, Optional, Tuple, Union


@dataclass
class Op:
    kind: str                     # input | const | add | sub | mul | neg | rot
    dst: str
    args: Tuple[str, ...] = ()
    values: Optional[List[Fraction]] = None      # const
    lo: Optional[Fraction] = None                # input
    hi: Optional[Fraction] = None                # input
    shift: Tuple[int, int] = (0, 0)              # rot: (coef of loop index, offset)


@dataclass
class Loop:
    n: Optional[int]                      # None = dynamic (public) trip count
    heads: List[Tuple[str, str]]          # (head name, init SSA name)
    body: List[Op]
    yields: List[str]
    results: List[str]                    # SSA names given to the loop results
    index: Optional[str] = None           # name of the induction variable (for rot)


Item = Union[Op, Loop]


@dataclass
class Program:
    name: str
    slots: int
    items: List[Item]
    returns: List[str]

    def inputs(self) -> List[Op]:
        return [it for it in self.items if isinstance(it, Op) and it.kind == "input"]

    def loops(self) -> List[Loop]:
        return [it for it in self.items if isinstance(it, Loop)]

    def has_rotation(self) -> bool:
        def rot(ops): return any(o.kind == "rot" for o in ops)
        return any(rot(it.body) if isinstance(it, Loop) else it.kind == "rot" for it in self.items)
