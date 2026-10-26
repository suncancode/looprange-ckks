"""verify_claims.py -- re-check the claims of the W22+23 report mechanically.

Independent of build_w22.py: every number is recomputed here from results/*.json, every
source citation is printed from the Lattigo module cache / HEIR output, and each check
prints PASS or FAIL with the evidence.  Run from src/:

    python3 verify_claims.py            # needs Go module cache with lattigo v6.2.0
"""
import glob, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
LAT = next(iter(glob.glob(os.path.expanduser("~/go/pkg/mod/github.com/tuneinsight/lattigo/v6@v6.2.0"))), None)
fails = 0


def check(name, ok, evidence=""):
    global fails
    fails += (not ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"\n        {evidence}" if evidence else ""))


def src_line(rel, n):
    return open(os.path.join(LAT, rel)).read().splitlines()[n - 1].strip()


def load(name):
    return json.load(open(os.path.join(ROOT, "results", name)))


print("== 1. Lattigo v6.2.0 source citations ==")
if not LAT:
    print("Lattigo module cache not found: run any E-step once (go build) first."); sys.exit(1)
for rel, n, pat, claim in [
    ("ring/scaling.go", 101, r"func \(r Ring\) DivRoundByLastModulusNTT", "rescaling = division by the last prime, modular"),
]:
    line = src_line(rel, n)
    check(f"{rel} l.{n}: {claim}", re.search(pat, line) is not None, line[:150])
enc = open(os.path.join(LAT, "schemes/ckks/encoder.go")).read().splitlines()[930:1000]
check("schemes/ckks/encoder.go l.931-1000: decoding centres the coefficients (c - Q when c >= Q/2)",
      any("c.Sub(c, Q)" in l for l in enc), next((l.strip() for l in enc if "c.Sub(c, Q)" in l), ""))

print("\n== 2. HEIR source (GenerateParamCKKS.cpp, commit e4497fb) ==")
_heir_src = (glob.glob(os.path.join(ROOT, "lit", "heir_source_e4497fb", "GenerateParamCKKS.cpp"))
             or glob.glob(os.path.join(ROOT, "..", "w20src", "w21_heir", "heir_source", "e4497fb", "GenerateParamCKKS.cpp")))
if not _heir_src:
    print("[SKIP] HEIR GenerateParamCKKS.cpp snapshot (e4497fb) not found next to W22/: HEIR source checks not run here")
for f in _heir_src:
    L = open(f).read().splitlines()
    check("HEIR GenerateParamCKKS.cpp (e4497fb) l.71: range analysis starts from the option inputRange",
          "Log2Arithmetic::of(inputRange)" in L[70], L[70].strip())
    check("HEIR GenerateParamCKKS.cpp (e4497fb) l.82: only values at level 0 are bounded",
          "getLevelFromMgmtAttr(result) == 0" in L[81], L[81].strip())
    check("HEIR GenerateParamCKKS.cpp (e4497fb) l.97-98: level0 bits = ceil(extra)+2 ('2 more bits for cushion')",
          "ceil(extraBits.value()) + 2" in L[97] and "cushion" in L[96], L[97].strip())
    check("HEIR GenerateParamCKKS.cpp (e4497fb) l.117: first = scaling + extra", "scalingModBits + extraBits.value()" in L[116], L[116].strip())

def macros():
    tex = open(os.path.join(ROOT, "report", "W22.tex")).read()
    return dict(re.findall(r"\\newcommand\{\\(\w+)\}\{(.*)\}", tex))


MAC = macros()


def mac_is(name, value_str):
    got = MAC.get(name)
    check(f"report macro \\{name} = {value_str} (recomputed from JSON)", got == value_str, f"report has {got!r}")


def sci(x):
    e = math.floor(math.log10(abs(x))); return f"${x / 10 ** e:.1f}\\times10^{{{e}}}$"


print("\n== 3. E1 (results/e1_obligation.json): with one bit too few, only constant inputs fail ==")
e1 = load("e1_obligation.json")
for r in e1["rows"]:
    if r["program"].startswith("c1"): continue
    run = r["at_out_minus1"]
    inp = json.load(open(os.path.join(ROOT, "runs", f"e1_{r['program'][:-5]}_{r['q0_out'] - 1}", "inputs.json")))
    bad = [list(inp[i].values())[0] for i, st in enumerate(run["sets"]) if not st["ok"]]
    const = all(len(set(v if isinstance(v, list) else [v])) == 1 for v in bad)
    check(f"{r['program']}: the failing sets at {r['q0_out'] - 1} bits are constant vectors", const and len(bad) > 0,
          f"{len(bad)} failing; first values {[ (v if isinstance(v, list) else [v])[:3] for v in bad]}")

print("\n== 4. tolerance gap (results/threshold_gap.json) ==")
tg = load("threshold_gap.json")
check("largest correct normalised error < 1e-3 < smallest wrong normalised error",
      tg["max_ok"]["norm_err"] < 1e-3 < tg["min_wrong"]["norm_err"], f"{tg['max_ok']['norm_err']:.3g} / {tg['min_wrong']['norm_err']:.3g}")
mac_is("ThrNOK", str(tg["n_ok"])); mac_is("ThrNWrong", str(tg["n_wrong"]))

print("\n== 5. E1 levels (results/e1_levels.json, from HEIR's IR) ==")
lv = load("e1_levels.json")
for k in ("w1_shift", "w3_loop", "w4_rot", "c1_control"):
    check(f"{k}: one prime, every operation at level 0", len(lv[k]["Q_bits"]) == 1 and lv[k]["body_levels"] == [0],
          f"Q_bits={lv[k]['Q_bits']} levels={lv[k]['body_levels']}")
w2 = lv["w2_square"]; mul = next(o for o in w2["ops"] if o["op"] == "arith.mulf")
check("w2_square: product at level 1 with scale Delta^2, output at level 0",
      mul["level"] == 1 and mul["deg"] == 2 and w2["out_level"] == 0, str(mul))
g2 = open(os.path.join(ROOT, "runs", f"e1_w2_square_{next(r['q0_out'] for r in e1['rows'] if r['program'].startswith('w2'))}", "prog.go.txt")).read()
check("w2_square generated code: the constant added after the product is encoded at scale 2^90 (= Delta^2)",
      "math.Pow(2, 90)" in g2)
mac_is("EOneWTwoMulCap", f"{mul['cap_log2']:.1f}"); mac_is("EOneWTwoOutCap", f"{w2['ops'][-1]['cap_log2']:.1f}")

print("\n== 6. Engine trace (results/trace_relax.json) and E3 ==")
tr = load("trace_relax.json")
check("trace: invariant(widened)@1, bound 8, 48 body evaluations",
      tr["loops"] == ["invariant(widened)@1"] and float(tr["B_out"]) == 8 and tr["evals"] == 48, f"{tr['loops']} {tr['B_out']} {tr['evals']}")
e3 = load("e3_methods.json")
dyn = e3["k3_relax"]["?"]["LoopRange"]
check("E3 k3_relax dynamic n uses the same 48 evaluations", dyn.get("evals") == 48, f"evals={dyn.get('evals')} status={dyn['status']}")

print(f"\n{fails} check(s) failed")
sys.exit(1 if fails else 0)
