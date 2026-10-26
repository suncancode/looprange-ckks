"""E6 -- rolled loops (HEIR 2026.10.1): why a bound valid for EVERY iteration matters.

HEIR 2026.10.1 keeps long loops rolled and places bootstrapping inside the loop body (W21,
E5).  Its own range analysis (first-mod-bits=0) is a fixpoint over a max-lattice without
widening, so on such a loop it does not terminate (issue #2754, reproduced in W21).
LoopRange gives a bound for every iteration from an inductive invariant.  Here we only
COMPILE (heir-opt ... --scheme-to-lattigo) with a time limit and record:
  - first-mod-bits=0           : does HEIR finish?  how long?
  - first-mod-bits=<LoopRange> : does HEIR finish?  is the loop still rolled (scf.for/affine.for
                                 in the output) and does it contain bootstrapping?
Running the generated code needs bootstrapping keys (N = 2^16), which needs more memory than the machines used here.

    HEIR101=/path/to/venv101/bin python3 run_e6_rolled.py
"""
import json, os, re, subprocess, sys, time
from exp_common import HERE, SCALE, bounds, env_report

HEIRBIN = os.environ.get("HEIR101", "")          # directory holding heir-opt 2026.10.1
TIMEOUT = int(os.environ.get("E6_TIMEOUT", "120"))
W = os.path.join(HERE, "..", "programs", "e5_workloads")
GEN = os.path.join(HERE, "..", "programs", "generated", "e6"); os.makedirs(GEN, exist_ok=True)
OUT = os.path.join(HERE, "..", "runs", "e6"); os.makedirs(OUT, exist_ok=True)


def compile_once(mlir, fmb, tag):
    opt = os.path.join(HEIRBIN, "heir-opt") if HEIRBIN else "heir-opt"
    opts = f"scaling-mod-bits={SCALE} first-mod-bits={fmb}"
    t0 = time.time()
    try:
        r = subprocess.run([opt, "--annotate-module=backend=lattigo scheme=ckks", f"--mlir-to-ckks={opts}",
                            "--scheme-to-lattigo", mlir], capture_output=True, text=True, timeout=TIMEOUT)
        dt = time.time() - t0
        out = r.stdout
        open(os.path.join(OUT, f"{tag}_fmb{fmb}.mlir"), "w").write(out)
        open(os.path.join(OUT, f"{tag}_fmb{fmb}.err"), "w").write(r.stderr)
        st = "ok" if r.returncode == 0 else (
            "HEIR error: rotation by the loop index in a rolled loop"
            if "failed to compute static rotation indices" in r.stderr else "error")
        return dict(status=st, seconds=round(dt, 2),
                    rolled=("scf.for" in out or "affine.for" in out),
                    bootstraps=len(re.findall(r"lattigo\.ckks\.bootstrap\b(?!_)", out)),
                    q0=_q0(out), message=r.stderr.strip().splitlines()[-1:] if r.returncode else None)
    except subprocess.TimeoutExpired:
        return dict(status=f"timeout (> {TIMEOUT} s)", seconds=TIMEOUT)


def _q0(out):
    import re, math
    m = re.search(r"Q = \[(\d+)", out)
    return round(math.log2(int(m.group(1)))) if m else None


def main():
    ver = subprocess.run([os.path.join(HEIRBIN, "heir-opt") if HEIRBIN else "heir-opt", "--version"],
                         capture_output=True, text=True).stdout
    log = {"env": env_report(), "heir_opt": ver.strip().splitlines()[:2], "rows": []}
    print("\n".join(log["env"])); print("heir-opt used:", HEIRBIN or "PATH")
    print(f"\n{'program':18s} {'n':>4s} {'LR mode':24s} {'LR q0':>6s} {'LR ms':>7s} | {'fmb=0':>22s} | {'fmb=LoopRange':>40s}")
    for w in ("heat", "ema"):
        for n in (20, 50, 100):
            p = os.path.join(GEN, f"{w}_n{n}.mlir")
            open(p, "w").write(open(os.path.join(W, w + ".mlir.in")).read()
                               .replace("@S@", "1024").replace("@SM1@", "1023").replace("@N@", str(n)))
            prog, b = bounds(p)
            lr = b["affine + invariant only"]          # the bound valid for every iteration
            q = lr["q0_out"]
            a = compile_once(p, 0, f"{w}_n{n}")
            l = compile_once(p, q, f"{w}_n{n}")
            row = dict(workload=w, n=n, lr_mode=lr["mode"], lr_q0=q, lr_ms=lr["seconds"] * 1e3, auto=a, looprange=l)
            log["rows"].append(row)
            ls = f"{l['status']} {l['seconds']}s rolled={l.get('rolled')} bts={l.get('bootstraps')} q0={l.get('q0')}"
            print(f"{w:18s} {n:4d} {lr['mode']:24s} {q:6d} {row['lr_ms']:7.1f} | {a['status'] + ' ' + str(a['seconds']) + 's':>22s} | {ls:>40s}")
    json.dump(log, open(os.path.join(HERE, "..", "results", "e6_rolled.json"), "w"), indent=1, default=str)
    print("wrote results/e6_rolled.json")


if __name__ == "__main__":
    main()
