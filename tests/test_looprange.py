"""Tests that need no FHE library: pure Python, exact rational arithmetic.

    python3 -m pytest -q tests
"""
import os, random, subprocess, sys
from fractions import Fraction as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src", "looprange3"))

import concrete                                   # noqa: E402
import fuzz                                       # noqa: E402
from analysis import METHODS, analyze, q0_bits    # noqa: E402
from mlir_reader import read                      # noqa: E402

PROG = os.path.join(ROOT, "programs")


def kernel(name, n, tmp_path):
    """Instantiate a template programs/e3_kernels/<name>.mlir.in with trip count n."""
    text = open(os.path.join(PROG, "e3_kernels", name + ".mlir.in")).read().replace("@N@", str(n))
    p = tmp_path / f"{name}_{n}.mlir"
    p.write_text(text)
    return str(p)


def test_ckks_toy_examples():
    """The hand-sized CKKS examples (encode, encrypt, decrypt, decode, wrap-around) all pass."""
    r = subprocess.run([sys.executable, os.path.join(ROOT, "src", "tools", "ckks_toy.py")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]
    assert "0 check(s) failed" in r.stdout


def test_q0_rule():
    """q0 bits = scale + ceil(log2 B) + 2 (the rule of HEIR's GenerateParamCKKS)."""
    assert q0_bits(45, F(1)) == 47
    assert q0_bits(45, F(2)) == 48
    assert q0_bits(45, F(3)) == 49
    assert q0_bits(45, None) is None


def test_e1_output_bounds():
    """E1 programs: LoopRange's OUT bound gives 47 bits (51 for the control C1)."""
    want = {"w1_shift": 47, "w2_square": 47, "w3_loop": 47, "w4_rot": 47, "c1_control": 51}
    for name, bits in want.items():
        r = analyze(read(os.path.join(PROG, "e1_obligation", name + ".mlir")), "affine", "looprange")
        assert r.status == "bounded"
        assert q0_bits(45, r.B_out) == bits, name


def test_dynamic_trip_count(tmp_path):
    """A dynamic trip count ('?') is bounded through the loop invariant; unrolling cannot."""
    p = kernel("k3_relax", "?", tmp_path)
    prog = read(p)
    assert analyze(prog, "affine", "looprange").status == "bounded"
    assert analyze(prog, "affine", "unroll").status != "bounded"


def test_divergent_loop_not_established(tmp_path):
    """x <- 1.3 x + 0.5 diverges: with a dynamic n the answer is 'bound not established'."""
    r = analyze(read(kernel("k6_divergent", "?", tmp_path)), "affine", "looprange")
    assert r.status != "bounded"


def test_bounds_hold_on_exact_runs(tmp_path):
    """Every value observed in exact runs of the kernels (n = 6) is within LoopRange's bound."""
    for name in ["k1_ema", "k2_gradient", "k3_relax", "k4_newton_recip", "k5_jacobi", "k7_alternating",
                 "k8_heat", "k9_newton_rsqrt", "k10_mask"]:
        prog = read(kernel(name, 6, tmp_path))
        r = analyze(prog, "affine", "looprange")
        assert r.status == "bounded", name
        R = random.Random(1)
        for pt in fuzz.corners(prog, R):
            _, trace = concrete.run(prog, pt)
            for v, mag in trace.items():
                if v in r.per_value:
                    assert mag <= r.per_value[v], (name, v, float(mag), float(r.per_value[v]))


def test_soundness_fuzz_small():
    """60 random programs (the E4 generator): no sound method ever exceeds its bound."""
    R = random.Random(7)
    sound = [m for m in METHODS if m != "HEIR (as implemented)"]
    for idx in range(60):
        prog = fuzz.rnd_program(R, idx)
        dyn = any(l.n is None for l in prog.loops())
        traces = []
        for pt in fuzz.corners(prog, R):
            for nd in (range(fuzz.N_DYN + 1) if dyn else [0]):
                try:
                    traces.append(concrete.run(prog, pt, n_dynamic=nd)[1])
                except OverflowError:
                    pass
        for m in sound:
            dom, strat = METHODS[m]
            r = analyze(prog, dom, strat)
            if r.status != "bounded":
                continue
            for tr in traces:
                for v, mag in tr.items():
                    if v in r.per_value:
                        assert mag <= r.per_value[v], (m, prog.name, v)
