"""E5 -- larger workloads: does a tighter, sound q0 save runtime and memory?

Two vector workloads on 1024 slots (programs/e5_workloads): heat diffusion with rotations,
and an exponential moving average written in the incremental form m + a(x - m).  For each
trip count n, HEIR compiles the program once per q0 policy and the generated Lattigo code
is run on three input sets (alternating +-1, all +1, uniform random in [-1, 1]).

Policies (all passed as first-mod-bits, except auto/default):
  HEIR auto   first-mod-bits=0           HEIR default   no option (55 bits)
  simple fix  OUT bound, sub = Ba + Bb   interval       OUT bound, signed intervals
  LR ALL      LoopRange, every value     LR OUT         LoopRange, returned value only
Measured: correctness, q0, log N, log QP, key generation + parameter time (configure),
mean evaluation time of F, and the process's peak resident memory (VmHWM).
"""
import json, os, sys, random
from exp_common import *

W = os.path.join(HERE, "..", "programs", "e5_workloads")
GEN = os.path.join(HERE, "..", "programs", "generated", "e5"); os.makedirs(GEN, exist_ok=True)
S = int(os.environ.get("E5_SLOTS", "1024"))
NS = [int(x) for x in os.environ.get("E5_NS", "2 4 5 6 7 8 10 12 14 16").split()]
WORKLOADS = os.environ.get("E5_WORKLOADS", "heat ema").split()
SUFFIX = os.environ.get("E5_SUFFIX", "")


def inputs(S, lo=-1.0, hi=1.0, seed=11):
    R = random.Random(seed)
    return [{"x": [hi if s % 2 else lo for s in range(S)]},
            {"x": [hi] * S},
            {"x": [R.uniform(lo, hi) for _ in range(S)]}]


def main():
    log = {"env": env_report(), "slots": S, "rows": []}
    print("\n".join(log["env"]))
    pols = ["HEIR auto", "HEIR default", "simple fix", "interval", "LR ALL", "LR OUT"]
    for w in WORKLOADS:
        print(f"\n=== {w}, {S} slots ===")
        print(f"{'n':>3s} {'policy':13s} {'q0':>4s} {'logN':>5s} {'logQP':>7s} {'result':>12s} {'max err':>9s} "
              f"{'keygen s':>9s} {'eval s':>8s} {'peak MB':>8s}")
        for n in NS:
            p = os.path.join(GEN, f"{w}_S{S}_n{n}.mlir")
            open(p, "w").write(open(os.path.join(W, w + ".mlir.in")).read()
                               .replace("@S@", str(S)).replace("@SM1@", str(S - 1)).replace("@N@", str(n)))
            prog, b = bounds(p)
            x = prog.inputs()[0]
            ins = inputs(S, float(x.lo), float(x.hi))
            fmbs = {"HEIR auto": 0, "HEIR default": "default",
                    "simple fix": b["simple fix"]["q0_out"], "interval": b["signed interval"]["q0_out"],
                    "LR ALL": b["LoopRange"]["q0_all"], "LR OUT": b["LoopRange"]["q0_out"]}
            for pol in pols:
                r = run(p, fmbs[pol], f"e5{w}{n}", ins)
                pr = r.get("params") or {}
                row = dict(workload=w, n=n, policy=pol, fmb=fmbs[pol], status=r["status"],
                           q0=q0_of(r) if pr else None, logN=pr.get("logN"), logQP=pr.get("logQP"),
                           max_err=r.get("max_err"), configure_s=r.get("configure_s"),
                           eval_s=r.get("eval_s"), mem_kb=r.get("mem_kb"), heir_opt_s=r.get("heir_opt_s"),
                           message=r.get("message"))
                log["rows"].append(row)
                if pr:
                    print(f"{n:3d} {pol:13s} {row['q0']:>4} {row['logN']:>5} {row['logQP']:7.1f} {row['status']:>12s} "
                          f"{row['max_err']:9.2g} {row['configure_s']:9.2f} {row['eval_s']:8.2f} {row['mem_kb']/1024:8.0f}")
                else:
                    print(f"{n:3d} {pol:13s} {str(fmbs[pol]):>4} {'-':>5} {'-':>7} {row['status']:>12s}   {str(row['message'])[:80]}")
                json.dump(log, open(os.path.join(HERE, "..", "results", f"e5_workload_S{S}{SUFFIX}.json"), "w"), indent=1, default=str)
    print(f"wrote results/e5_workload_S{S}{SUFFIX}.json")


if __name__ == "__main__":
    main()
