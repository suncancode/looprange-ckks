"""threshold_gap.py -- how much does the choice of the error tolerance matter?

For every input set of every real HEIR+Lattigo run in results/ (E1, E2, E5, E5-C), take the
normalised error  err / max(1, |exact|)  and split the sets into correct and wrong ones.
Any tolerance strictly between the largest normalised error of a correct set and the
smallest normalised error of a wrong set gives exactly the same classification.

    python3 threshold_gap.py        -> results/threshold_gap.json
"""
import glob, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
FILES = ["e1_obligation.json", "e2_table.json"] + sorted(
    os.path.basename(f) for f in glob.glob(os.path.join(RES, "e5_workload_S*.json")))


def walk(o, path, ok, bad):
    if isinstance(o, dict):
        if isinstance(o.get("status"), str) and o.get("sets"):
            for i, s in enumerate(o["sets"]):
                n = s["err"] / max(1.0, s["ref_max"])
                (ok if s["ok"] else bad).append(dict(norm_err=n, err=s["err"], ref_max=s["ref_max"],
                                                     where=f"{path} set {i}"))
        for k, v in o.items():
            walk(v, f"{path}/{k}", ok, bad)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, f"{path}[{i}]", ok, bad)


def main():
    ok, bad, used = [], [], []
    for f in FILES:
        p = os.path.join(RES, f)
        if os.path.exists(p):
            walk(json.load(open(p)), f, ok, bad); used.append(f)
    out = dict(files=used, n_ok=len(ok), n_wrong=len(bad),
               max_ok=max(ok, key=lambda r: r["norm_err"]) if ok else None,
               min_wrong=min(bad, key=lambda r: r["norm_err"]) if bad else None)
    json.dump(out, open(os.path.join(RES, "threshold_gap.json"), "w"), indent=1)
    print(f"files: {used}")
    print(f"correct input sets: {out['n_ok']}, largest normalised error {out['max_ok']['norm_err']:.3g} ({out['max_ok']['where']})")
    if bad:
        print(f"wrong input sets:   {out['n_wrong']}, smallest normalised error {out['min_wrong']['norm_err']:.3g} ({out['min_wrong']['where']})")
    print("any tolerance strictly between these two numbers gives the same classification")
    print("wrote results/threshold_gap.json")


if __name__ == "__main__":
    main()
