"""exp_common.py -- shared helpers for the W22 experiment scripts."""
from __future__ import annotations
import json, os, random, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "looprange3"))
from mlir_reader import read
from analysis import analyze, q0_bits, METHODS
import heirrun

RUNS = os.environ.get("W22_RUNS", os.path.join(HERE, "..", "runs"))
SCALE = 45


def env_report():
    def ver(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True).stdout.strip().splitlines()
        except Exception as e:
            return [repr(e)]
    lines = [time.strftime("%Y-%m-%d %H:%M:%S %Z"),
             "heir-opt: " + " ".join(ver(["heir-opt", "--version"])[1:2]),
             "heir_py: " + " ".join(l for l in ver([sys.executable, "-m", "pip", "show", "heir_py"]) if l.startswith("Version")),
             "go: " + " ".join(ver([heirrun.GO, "version"])),
             "python: " + sys.version.split()[0],
             "cpu: " + next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), "?"),
             "nproc: " + str(os.cpu_count()),
             "mem: " + next((f"{int(l.split()[1]) / 2**20:.1f} GB" for l in open("/proc/meminfo") if l.startswith("MemTotal")), "?")]
    return lines


def inputs_for(prog, k_random=3, seed=7):
    """Input sets: every corner of the input box (each input all-lo / all-hi), a few interior
    points, and (vectors) alternating-sign and random patterns.  All inside HEIR's [-1, 1]."""
    R = random.Random(seed)
    ins = prog.inputs(); S = prog.slots
    sets = []
    import itertools
    for c in itertools.product(*[(float(o.lo), float(o.hi)) for o in ins]):
        sets.append({o.dst: (c[i] if S == 1 else [c[i]] * S) for i, o in enumerate(ins)})
    for t in (0.3, -0.5, 0.0):
        sets.append({o.dst: (t if S == 1 else [t] * S) for o in ins})
    if S > 1:
        sets.append({o.dst: [float(o.hi) if s % 2 else float(o.lo) for s in range(S)] for o in ins})
        for _ in range(k_random):
            sets.append({o.dst: [R.uniform(float(o.lo), float(o.hi)) for _ in range(S)] for o in ins})
    return sets


def bounds(mlir):
    prog = read(mlir)
    out = {}
    for name, (dom, strat) in METHODS.items():
        r = analyze(prog, dom, strat)
        out[name] = dict(status=r.status, B_out=r.B_out, B_all=r.B_all,
                         q0_out=q0_bits(SCALE, r.B_out), q0_all=q0_bits(SCALE, r.B_all),
                         mode=";".join(l.mode for l in r.loops) or "straight-line",
                         evals=r.evals, seconds=r.seconds)
    return prog, out


_cache = {}


def run(mlir, fmb, tag, inputs, keep_ir=False):
    key = (os.path.abspath(mlir), fmb)
    if key in _cache: return _cache[key]
    name = re.sub(r"[^A-Za-z0-9_]", "_", f"{tag}_{os.path.basename(mlir)[:-5]}_{fmb}")
    res = heirrun.compile_and_run(mlir, fmb, inputs, os.path.join(RUNS, name), name, keep_ir=keep_ir)
    _cache[key] = res
    return res


def smallest_passing(mlir, tag, inputs, lo, hi):
    """Smallest first-mod-bits in [lo, hi] for which every input set is correct (real runs,
    ascending).  Returns (bits or None, list of (bits, status))."""
    tried = []
    for b in range(lo, hi + 1):
        r = run(mlir, b, tag, inputs)
        tried.append((b, r["status"]))
        if r["status"] == "OK":
            return b, tried
    return None, tried


def cell(r):
    if r is None: return "-"
    if r["status"] == "OK": return f"{q0_of(r)}"
    if r["status"].startswith("WRONG"): return f"{q0_of(r)} WRONG{r['status'][5:]}"
    return r["status"]


def q0_of(r):
    p = r.get("params") or {}
    qb = p.get("Q_bits")
    return round(qb[0]) if qb else "?"
