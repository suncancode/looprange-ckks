"""trace_engine.py -- record what the LoopRange engine does on one loop, step by step.

The trace is produced by the real engine (looprange3.analysis.Engine); this script only
wraps run_body/check to log the boxes.  Used for the worked example in the report
(Appendix A, Table "trace").

    python3 trace_engine.py ../programs/w20_table2/relax.mlir.in   -> results/trace_relax.json
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "looprange3"))
from mlir_reader import read
from analysis import Engine


class Tracing(Engine):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.events, self.k = [], 0

    def run_body(self, loop, state, env, index, record=True):
        e = super().run_body(loop, state, env, index, record)
        if record:                       # a forward step (checks call run_body with record=False)
            self.k += 1
            y = loop.yields[0]
            self.events.append(dict(kind="forward", k=self.k, box=[str(v) for v in self.D.box(e[y])]))
        return e

    def check(self, loop, S, env):
        ok, envs = super().check(loop, S, env)
        h = loop.heads[0][0]
        ev = self.evals                  # the extra run below is for the log only: not counted
        img = self.image_box(loop, S, env)[h]
        self.evals = ev
        self.events.append(dict(kind="check", k=self.k, S=[str(v) for v in S[h]],
                                image=[str(v) for v in img], ok=ok))
        return ok, envs


def main():
    src = sys.argv[1]
    text = open(src).read().replace("@N@", "?")       # dynamic trip count
    tmp = os.path.join(HERE, "..", "programs", "generated", "trace_" + os.path.basename(src).replace(".in", ""))
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    open(tmp, "w").write(text)
    prog = read(tmp)
    eng = Tracing(prog, "affine", "invariant")
    res = eng.run()
    out = dict(program=os.path.basename(src), n="dynamic", status=res.status,
               B_out=str(res.B_out), loops=[l.mode for l in res.loops], evals=res.evals, events=eng.events)
    name = os.path.basename(src).split(".")[0]
    p = os.path.join(HERE, "..", "results", f"trace_{name}.json")
    json.dump(out, open(p, "w"), indent=1)
    for e in eng.events: print(e)
    print(res.status, res.B_out, [l.mode for l in res.loops], "evals", res.evals)
    print("wrote", p)


if __name__ == "__main__":
    main()
