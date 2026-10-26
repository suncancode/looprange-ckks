"""build_w22.py -- fill the %%AUTO blocks of W22.tex from results/*.json.

No number is typed into the report by hand: every number in a table or a macro comes from
the JSON files written by the experiment scripts.

    python3 build_w22.py ../../report/W22.tex [--source "the sandbox"|"WSL2"]
"""
from fractions import Fraction as F
import json, os, re, sys, math

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "..", "results")


def load(name):
    p = os.path.join(RES, name)
    return json.load(open(p)) if os.path.exists(p) else None


def mac(name, val):
    return f"\\newcommand{{\\{name}}}{{{val}}}\n"


def sci(x):
    if x is None: return "--"
    if x == 0: return "0"
    e = math.floor(math.log10(abs(x))); m = x / 10 ** e
    return f"${m:.1f}\\times10^{{{e}}}$"


OPTIONAL_BLOCKS = set()
WIDE_BLOCKS = {"e5", "e5c", "e6"}         # tables wider than the text: scaled to the text width


def put(tex, block, body):
    pat = re.compile(rf"(%%AUTO:{block}:BEGIN\n)(.*?)(%%AUTO:{block}:END)", re.S)
    if not pat.search(tex):
        if block in OPTIONAL_BLOCKS:
            print(f"(block {block} not in this .tex: skipped)"); return tex
        raise SystemExit(f"block {block} missing")
    if block in WIDE_BLOCKS and "\\resizebox" not in body:
        body = body.replace("\\begin{tabular}", "\\resizebox{\\textwidth}{!}{%\n\\begin{tabular}").replace(
            "\\end{tabular}", "\\end{tabular}}")
    return pat.sub(lambda m: m.group(1) + body + m.group(3), tex)


def q0(r):
    p = r.get("params") or {}
    return round(p["Q_bits"][0]) if p.get("Q_bits") else None


def cellrun(r):
    if r is None: return "--"
    st = r["status"]
    if st == "OK": return f"{q0(r)}\\,\\checkmark"
    if st.startswith("WRONG"): return f"\\textbf{{{q0(r)}}}\\,\\xmark\\,{st[6:-1]}"
    return st


DESC = {"w1_shift": "$(x+1000)-1000$", "w2_square": "$(x+64)(x-64)+4096$",
        "w3_loop": "8$\\times$: $x\\leftarrow 0.5-((x+512)-512)$", "w4_rot": "$\\mathrm{rot}(x+1000,1)-1000$, 16 slots",
        "c1_control": "control: $(x+1000)-990$"}


def main():
    tex_path = sys.argv[1]
    source = sys.argv[sys.argv.index("--source") + 1] if "--source" in sys.argv else "the sandbox"
    if source == "provenance":
        # results/provenance.json is written by run_w22_wsl2.sh: which steps ran on WSL2
        prov = load("provenance.json") or {}
        exps = [k for k in ("E1", "E2", "E3", "E4", "E5", "E5C", "E6", "TR")
                if k in prov and prov[k].get("machine") == "WSL2" and prov[k].get("status") == 0]
        source = ("WSL2 (run of record) for " + ", ".join(exps) + "; the sandbox (provisional) for the other experiments"
                  if exps else "the sandbox (provisional)")
    tex = open(tex_path).read()
    m = mac("DataSource", source)
    provd = load("provenance.json") or {}
    for k, name in (("E1", "SrcEOne"), ("E2", "SrcETwo"), ("E3", "SrcEThree"), ("E4", "SrcEFour"),
                    ("E5", "SrcEFive"), ("E5C", "SrcEFiveC"), ("E6", "SrcESix"), ("TR", "SrcTrace")):
        pv = provd.get(k, {})
        m += mac(name, "WSL2" if pv.get("machine") == "WSL2" and pv.get("status") == 0 else "sandbox, provisional")
    ok_errs = []

    # ---------------------------------------------------------------- E1
    e1 = load("e1_obligation.json")
    rows = ""
    if e1:
        order = ["w1_shift", "w2_square", "w3_loop", "w4_rot", "c1_control"]
        R = {r["program"][:-5]: r for r in e1["rows"]}
        maxover, maxerr = 0, 0
        LV = load("e1_levels.json") or {}
        lvtxt = lambda k: ("$\\to$".join(str(l) for l in LV[k]["body_levels"]) if k in LV else "--")
        for k in order:
            r = R.get(k)
            if not r: continue
            rows += (f"{k.split('_')[0].upper()} & {DESC[k]} & {r['q0_out']} & {r['q0_all']} & {lvtxt(k)} & "
                     f"{r['intermediate_over_cap']:.0f}$\\times$ & {cellrun(r['at_out'])} & "
                     f"{cellrun(r['at_out_minus1'])} & {cellrun(r.get('at_47'))} & {r['smallest']} \\\\\n")
            if k != "c1_control":
                maxover = max(maxover, r["intermediate_over_cap"])
                if r["at_out"]["status"] == "OK": maxerr = max(maxerr, r["at_out"]["max_err"])
            for kk in ("at_out", "at_all", "auto", "at_out_minus1", "at_47"):
                if r.get(kk) and r[kk].get("status") == "OK": ok_errs.append(r[kk]["max_err"])
        m += mac("EOneMaxOver", f"{maxover:.0f}") + mac("EOneMaxErr", sci(maxerr))
        if "w2_square" in LV:
            ops = LV["w2_square"]["ops"]
            mul = next(o for o in ops if o["op"] == "arith.mulf")
            out = ops[-1]
            m += (mac("EOneWTwoMulLevel", mul["level"]) + mac("EOneWTwoMulDeg", mul["deg"])
                  + mac("EOneWTwoMulCap", f"{mul['cap_log2']:.1f}") + mac("EOneWTwoOutCap", f"{out['cap_log2']:.1f}"))
        one = [k for k in ("w1_shift", "w3_loop", "w4_rot", "c1_control") if k in LV and LV[k]["body_levels"] == [0]
               and len(LV[k]["Q_bits"]) == 1]
        m += mac("EOneSinglePrime", ", ".join(k.split("_")[0].upper() for k in one))
    tex = put(tex, "e1", rows)

    # ---------------------------------------------------------------- E2
    e2 = load("e2_table.json")
    rows = ""
    if e2:
        heir_wrong, slack, okmax, badmin = 0, 0, 0, None
        prev = None
        for r in e2["rows"]:
            name = r["program"][:-5]
            base = re.sub(r"_n\d+$", "", name)
            if prev is not None and base != prev: rows += "\\addlinespace[2pt]\n"
            prev = base
            pretty = {"sub": "$y=x-z$", "mulsub": "$y=0.5-64x$"}.get(name)
            if pretty is None:
                n = name.rsplit("_n", 1)[1]
                body = {"loop_alt": "$x\\leftarrow1-x$", "relax": "$x\\leftarrow x-0.25(x-8)$"}[base]
                pretty = f"{body}, $n={n}$"
            lr = r["bounds"]["LoopRange"]
            runs = r["runs"]
            rows += (f"{pretty} & {cellrun(runs['auto'])} & {cellrun(runs['simple'])} & {cellrun(runs['interval'])} & "
                     f"{cellrun(runs['lr_out'])} & {cellrun(runs['lr_all'])} & {r['smallest']} & "
                     f"{lr['B_out']:.3g} / {lr['B_all']:.3g} \\\\\n")
            heir_wrong += runs["auto"]["status"].startswith("WRONG")
            if r["smallest"] is not None: slack = max(slack, q0(runs["lr_out"]) - r["smallest"])
            for x in runs.values():
                if x.get("status") == "OK": okmax = max(okmax, x["max_err"]); ok_errs.append(x["max_err"])
                elif str(x.get("status", "")).startswith("WRONG"):
                    badmin = x["max_err"] if badmin is None else min(badmin, x["max_err"])
        m += (mac("ETwoHeirWrong", heir_wrong) + mac("ETwoPrograms", len(e2["rows"])) + mac("ETwoMaxSlack", slack)
              + mac("ETwoMaxErrOK", sci(okmax)) + mac("ETwoMinErrWrong", f"{badmin:.3g}" if badmin else "--"))
    tex = put(tex, "e2", rows)

    # ---------------------------------------------------------------- E3
    e3 = load("e3_methods.json")
    rows = ""
    if e3:
        show = ["HEIR (as implemented)", "simple fix", "signed interval", "standard affine (unrolled)",
                "simple fix + invariant", "interval + invariant", "LoopRange"]
        inv_max = 0
        for k, byn in e3.items():
            label = "$k_{" + k.split("_")[0][1:] + "}$ " + k.split("_", 1)[1].replace("_", " ")
            for i, (n, row) in enumerate(byn.items()):
                cells = []
                for meth in show:
                    q = row[meth]["q0"]
                    cells.append("\\NE" if q is None else (f"{q}" if q < 100 else f"{q}"))
                obs = ""
                if "observed" in row and row["observed"] > 0:
                    b = 45 + max(0, math.ceil(math.log2(row["observed"]) - 1e-12)) + 2 if row["observed"] > 1 else \
                        45 + math.ceil(math.log2(row["observed"])) + 2
                    obs = f"{row['observed']:.3g} ({b})"
                rows += (f"{label if i == 0 else ''} & {'?' if n == '?' else n} & " + " & ".join(cells) + f" & {obs} \\\\\n")
            rows += "\\addlinespace[1pt]\n"
            dyn = byn["?"]["LoopRange"]
            if dyn["status"] == "bounded":
                inv_max = max(inv_max, dyn["evals"])
        static = [(k, n) for k, byn in e3.items() for n in byn if n != "?"]
        aa_eq = sum(e3[k][n]["standard affine (unrolled)"]["q0"] == e3[k][n]["LoopRange"]["q0"] for k, n in static)
        dyn_ok = lambda meth: [k for k in e3 if e3[k]["?"][meth]["status"] == "bounded"]
        nm = lambda ks: ", ".join("$k_{" + k.split("_")[0][1:] + "}$" for k in ks) or "none"
        m += (mac("EThreeStaticRows", len(static)) + mac("EThreeAAEqual", aa_eq)
              + mac("EThreeDynLR", len(dyn_ok("LoopRange"))) + mac("EThreeKernels", len(e3))
              + mac("EThreeDynIntvList", nm(dyn_ok("interval + invariant")))
              + mac("EThreeDynSimpleList", nm(dyn_ok("simple fix + invariant"))))
        g = lambda k, n, meth: e3[k][n][meth]["q0"]
        m += (mac("EThreeRelaxSimple", g("k3_relax", "1000", "simple fix")) + mac("EThreeRelaxLR", g("k3_relax", "1000", "LoopRange"))
              + mac("EThreeHeatSimple", g("k8_heat", "1000", "simple fix")) + mac("EThreeHeatLR", g("k8_heat", "1000", "LoopRange"))
              + mac("EThreeInvEvalsMax", inv_max) + mac("EThreeMaskLR", g("k10_mask", "10", "LoopRange")))
        grows = lambda meth: [k for k in e3 if all(g(k, n, meth) is not None for n in ("10", "1000"))
                              and g(k, "1000", meth) > g(k, "10", meth)]
        lr_flat = [k for k in e3 if all(g(k, n, "LoopRange") is not None for n in ("10", "100", "1000"))
                   and g(k, "10", "LoopRange") == g(k, "1000", "LoopRange")]
        m += (mac("EThreeSimpleGrow", nm([k for k in grows("simple fix") if k in lr_flat]))
              + mac("EThreeIntvGrow", nm([k for k in grows("signed interval") if k in lr_flat]))
              + mac("EThreeLRFlat", nm(lr_flat)))
    tex = put(tex, "e3", rows)

    # ---------------------------------------------------------------- E4
    e4 = load("e4_fuzz.json")
    body = ""
    if e4:
        body = ("\\begin{table}[H]\n\\centering\n\\caption{E4: soundness fuzz (seed " + str(e4["seed"]) +
                "). ``violated'': programs in which some value exceeded its bound.}\n\\label{tab:e4}\n\\scriptsize\n"
                "\\begin{tabular}{@{}lrrr@{}}\n\\toprule\nMethod & bounded & not established & violated \\\\\n\\midrule\n")
        for meth, s in e4["stats"].items():
            body += f"{meth} & {s['bounded']} & {s['not_est']} & {s['viol']} \\\\\n"
        body += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
        m += mac("EFourCount", e4["count"])
        m += mac("EFourHeirViol", e4["stats"]["HEIR (as implemented)"]["viol"])
    tex = put(tex, "e4", body)

    # ---------------------------------------------------------------- E5
    e5 = None
    for f in sorted(os.listdir(RES)) if os.path.isdir(RES) else []:
        if f.startswith("e5_workload_S") and "_raw" not in f:
            d = load(f)
            if e5 is None: e5 = d
            else: e5["rows"] += d["rows"]
    body = ""
    if e5:
        env = e5["env"]
        cpu = next((l.split(": ", 1)[1] for l in env if l.startswith("cpu")), "?")
        npr = next((l.split(": ", 1)[1] for l in env if l.startswith("nproc")), "?")
        cpu1 = cpu.split(" Intel(R)")[0].split(" AMD")[0] if cpu.count("GHz") > 1 else cpu
        mem = next((l.split(": ", 1)[1] for l in env if l.startswith("mem")), None)
        m += mac("EFiveMachine", f"{cpu1}, {npr} cores" + (f", {mem} RAM" if mem else ""))
        pols = ["HEIR auto", "HEIR default", "simple fix", "interval", "LR ALL", "LR OUT"]
        short = {"HEIR auto": "HEIR auto", "HEIR default": "default 55", "simple fix": "simple fix",
                 "interval": "interval", "LR ALL": "LR ALL", "LR OUT": "LR OUT"}
        for w in dict.fromkeys(r["workload"] for r in e5["rows"]):
            title = {"heat": "heat diffusion", "ema": "moving average"}[w]
            body += ("\\begin{table}[H]\n\\centering\n\\caption{E5, " + title + ", " + str(e5["slots"]) +
                     " slots. $q_0$ bits per policy (\\xmark: wrong result; crash: HEIR aborted), the ring dimension"
                     " $\\log_2 N$ HEIR selected (the same for every policy that compiled), and the range over the"
                     " policies of the evaluation time and of the peak memory.}\n\\label{tab:e5" + w + "}\n\\scriptsize\n"
                     "\\setlength{\\tabcolsep}{3.5pt}\n\\begin{tabular}{@{}r" + "r" * len(pols) + "rrr@{}}\n\\toprule\n$n$ & " +
                     " & ".join(short[p] for p in pols) + " & $\\log_2 N$ & eval (s) & memory (MB) \\\\\n\\midrule\n")
            for n in dict.fromkeys(r["n"] for r in e5["rows"] if r["workload"] == w):
                cells, logn, ts, ms = [], set(), [], []
                for p in pols:
                    r = next((x for x in e5["rows"] if x["workload"] == w and x["n"] == n and x["policy"] == p), None)
                    if r is None: cells.append("--"); continue
                    if r["q0"] is None:
                        cells.append(f"{r['fmb']} crash" if r["status"] == "REFUSED" else r["status"]); continue
                    mark = "" if r["status"] == "OK" else "\\,\\xmark"
                    if r["status"] == "OK": ok_errs.append(r["max_err"])
                    cells.append(f"{r['q0']}{mark}"); logn.add(r["logN"]); ts.append(r["eval_s"]); ms.append(r["mem_kb"] / 1024)
                ln = "/".join(str(x) for x in sorted(logn))
                body += (f"{n} & " + " & ".join(cells) + f" & {ln} & {min(ts):.2f}--{max(ts):.2f} & {min(ms):.0f}--{max(ms):.0f} \\\\\n")
            body += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
    tex = put(tex, "e5", body)

    if e5:
        rows5 = [r for r in e5["rows"] if r["workload"] in ("heat", "ema")]
        lr_out = sorted({r["q0"] for r in rows5 if r["policy"] == "LR OUT" and r["q0"]})
        lr_all = max(r["q0"] for r in rows5 if r["policy"] == "LR ALL" and r["q0"])
        fail = [r["n"] for r in rows5 if r["workload"] == "heat" and r["policy"] == "simple fix" and r["status"] != "OK"]
        heir = [r for r in rows5 if r["workload"] == "heat" and r["policy"] == "HEIR auto" and r["q0"]]
        byn = {}
        for r in rows5:
            if r["logN"]: byn.setdefault(r["n"], set()).add(r["logN"])
        same = all(len(v) == 1 for v in byn.values())
        # describe N ranges
        groups = {}
        for n, v in sorted(byn.items()): groups.setdefault(min(v), []).append(n)
        nr = "; ".join(f"$N=2^{{{k}}}$ for $n\\in\\{{{','.join(map(str, ns))}\\}}$" for k, ns in sorted(groups.items()))
        h16 = [r for r in rows5 if r["workload"] == "heat" and r["n"] == 16 and r["eval_s"]]
        shares, diffs = [], []
        for (w_, n_) in {(r["workload"], r["n"]) for r in rows5}:
            ok5 = [r for r in rows5 if r["workload"] == w_ and r["n"] == n_ and r["status"] == "OK"]
            d = max(r["q0"] for r in ok5) - min(r["q0"] for r in ok5)
            diffs.append(d); shares.append(100 * d / max(r["logQP"] for r in ok5))
        m += (mac("EFiveQDiffMax", max(diffs)) + mac("EFiveQShareMin", f"{min(shares):.1f}")
              + mac("EFiveQShareMax", f"{max(shares):.1f}")
              + mac("EFiveLogQPMin", f"{min(r['logQP'] for r in rows5 if r['logQP']):.0f}")
              + mac("EFiveLogQPMax", f"{max(r['logQP'] for r in rows5 if r['logQP']):.0f}"))
        m += (mac("EFiveLROut", "/".join(map(str, lr_out))) + mac("EFiveLRAllMax", lr_all)
              + mac("EFiveHeatFailN", min(fail) if fail else "--")
              + mac("EFiveHeirFirst", heir[0]["q0"]) + mac("EFiveHeirLast", heir[-1]["q0"])
              + mac("EFiveNRange", nr + ("" if same else " (not identical!)"))
              + mac("EFiveHeatSixteenTime", f"{min(r['eval_s'] for r in h16):.1f}--{max(r['eval_s'] for r in h16):.1f}")
              + mac("EFiveHeatSixteenMem", f"{min(r['mem_kb'] for r in h16)/1024:.0f}--{max(r['mem_kb'] for r in h16)/1024:.0f}"))
    # ---------------------------------------------------------------- E5-C (raw data)
    raw = None
    for f in sorted(os.listdir(RES)):
        if f.startswith("e5_workload_S") and "_raw" in f: raw = load(f)
    body = ""
    if raw:
        pols = ["HEIR auto", "HEIR default", "simple fix", "interval", "LR ALL", "LR OUT"]
        body = ("\\begin{table}[H]\n\\centering\n\\caption{E5-C, moving average on raw counts, " + str(raw["slots"]) +
                " slots. $q_0$ bits / $\\log_2 N$; \\xmark: wrong (wrong inputs / all inputs), with the largest error.}\n"
                "\\label{tab:e5c}\n\\scriptsize\n\\begin{tabular}{@{}r" + "l" * len(pols) + "@{}}\n\\toprule\n$n$ & " +
                " & ".join(["HEIR auto", "default 55", "simple fix", "interval", "LR ALL", "LR OUT"]) + " \\\\\n\\midrule\n")
        for n in dict.fromkeys(r["n"] for r in raw["rows"]):
            cells = []
            for p_ in pols:
                r = next((x for x in raw["rows"] if x["n"] == n and x["policy"] == p_), None)
                if r is None: cells.append("--"); continue
                if r["q0"] is None:
                    cells.append(f"{r['fmb']} crash" if r["status"] == "REFUSED" else r["status"]); continue
                if r["status"] == "OK":
                    cells.append(f"{r['q0']}/{r['logN']}"); ok_errs.append(r["max_err"])
                else:
                    cells.append(f"\\textbf{{{r['q0']}}}/{r['logN']}\\,\\xmark\\,{r['status'][6:-1]} ({r['max_err']:.3g})")
            body += f"{n} & " + " & ".join(cells) + " \\\\\n"
        body += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
        lrq = sorted({x["q0"] for x in raw["rows"] if x["policy"] == "LR OUT" and x["q0"]})
        failn = [x["n"] for x in raw["rows"] if x["policy"] == "simple fix" and x["status"] == "REFUSED"]
        errs = [x["max_err"] for x in raw["rows"] if x["policy"] in ("HEIR default", "HEIR auto") and str(x["status"]).startswith("WRONG")]
        m += (mac("ERawLR", "/".join(map(str, lrq))) + mac("ERawFailN", min(failn) if failn else "--")
              + mac("ERawErr", f"{min(errs):.0f}" if errs else "--"))
    tex = put(tex, "e5c", body)
    # ---------------------------------------------------------------- E6 (rolled loops)
    e6 = load("e6_rolled.json")
    body = ""
    if e6:
        body = ("\\begin{table}[H]\n\\centering\n\\caption{E6, HEIR (heir\\_py 2026.10.1), 1024 slots, compile only."
                " LoopRange: the invariant it found, its $q_0$ and its analysis time.}\n"
                "\\label{tab:e6}\n\\scriptsize\n\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{@{}lrlrrll@{}}\n\\toprule\n"
                "Workload & $n$ & LoopRange & $q_0$ & ms & HEIR alone & HEIR with LoopRange's $q_0$ \\\\\n\\midrule\n")
        for r in e6["rows"]:
            a, l = r["auto"], r["looprange"]
            fa = (f"compiled, {a['seconds']} s" if a["status"] == "ok" else
                  a["status"].replace("timeout (> ", "no result after $>$").replace(" s)", "~s"))
            fl = (f"compiled, {l['seconds']} s" + (", loop rolled" if l.get("rolled") else ", unrolled")
                  + (f", {l.get('bootstraps')} bootstraps in body" if l.get("bootstraps") else "")) if l["status"] == "ok" else \
                 ("HEIR error: failed to compute static rotation indices" if "rotation" in l["status"] else l["status"])
            body += f"{r['workload']} & {r['n']} & {r['lr_mode']} & {r['lr_q0']} & {r['lr_ms']:.1f} & {fa} & {fl} \\\\\n"
        body += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
    tex = put(tex, "e6", body)

    # ---------------------------------------------------------------- code size
    lr_dir = os.path.join(os.path.dirname(RES), "src", "looprange3")
    nlines = sum(sum(1 for _ in open(os.path.join(lr_dir, f))) for f in os.listdir(lr_dir) if f.endswith(".py"))
    m += mac("LRLines", nlines)

    # ---------------------------------------------------------------- engine trace (Appendix)
    tr = load("trace_relax.json")
    body = ""
    if tr:
        fx = lambda v: f"{float(F(v)):g}"
        body = ("\\begin{table}[H]\n\\centering\n\\caption{Trace of the real engine on $x\\leftarrow x-0.25(x-8)$, "
                "$x\\in[-1,1]$, dynamic $n$ (\\op{trace\\_engine.py}). $T(S)$: the box of the yielded value when the "
                "body is run once on a fresh form over $S$.}\n\\label{tab:trace}\n\\scriptsize\n"
                "\\begin{tabular}{@{}rllll@{}}\n\\toprule\nStep & $k$ & what & box & result \\\\\n\\midrule\n")
        for i, e in enumerate(tr["events"], 1):
            if e["kind"] == "forward":
                body += f"{i} & {e['k']} & forward step & $x_{{{e['k']}}}\\in[{fx(e['box'][0])},{fx(e['box'][1])}]$ & hull updated \\\\\n"
            else:
                res = "\\textbf{inductive}" if e["ok"] else "not inductive"
                body += (f"{i} & {e['k']} & test $S=[{fx(e['S'][0])},{fx(e['S'][1])}]$ & "
                         f"$T(S)=[{fx(e['image'][0])},{fx(e['image'][1])}]$ & {res} \\\\\n")
        body += "\\bottomrule\n\\end{tabular}\n\\end{table}\n"
        m += (mac("TraceStatus", tr["loops"][0]) + mac("TraceB", fx(tr["B_out"])) + mac("TraceEvals", tr["evals"]))
    tex = put(tex, "trace", body)



    # ---------------------------------------------------------------- tolerance gap (all real runs)
    tg = load("threshold_gap.json")
    if tg and tg.get("max_ok") and tg.get("min_wrong"):
        m += (mac("ThrNOK", tg["n_ok"]) + mac("ThrNWrong", tg["n_wrong"])
              + mac("ThrMaxOK", sci(tg["max_ok"]["norm_err"])) + mac("ThrMinWrong", f"{tg['min_wrong']['norm_err']:.2g}"))
    else:
        m += mac("ThrNOK", "--") + mac("ThrNWrong", "--") + mac("ThrMaxOK", "--") + mac("ThrMinWrong", "--")

    m += mac("EAllMaxErrOK", sci(max(ok_errs)) if ok_errs else "--")
    tex = put(tex, "macros", m)
    open(tex_path, "w").write(tex)
    print("filled", tex_path, "from", RES)


if __name__ == "__main__":
    main()
