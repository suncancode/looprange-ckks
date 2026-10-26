#!/usr/bin/env bash
# Reproduce and check the experiments of the LoopRange report (written for WSL2 / Ubuntu).
#
#   source <venv>/bin/activate                 # a Python environment with heir_py==2026.9.1
#   bash run_w22_wsl2.sh 2>&1 | tee run.log    # default = STEPS=CHECK (~10 min)
#
# Presets
#   CHECK  = TOY SLOTS TR E1 E1L E2 GAP BUILD VERIFY      (~10 min)
#   FULL   = TOY SLOTS TR E1 E1L E2 E3 E4 E5 GAP BUILD VERIFY   (~1 h)
#   or any list, e.g.  STEPS="E3 E4" bash run_w22_wsl2.sh
#
# Steps (each writes results/<name>.json and logs/<name>_wsl2.log)
#   TOY    the hand-sized CKKS examples (encode, keygen, encrypt, decrypt, decode, wrap) -- pure Python
#   SLOTS  Lattigo: how 1024 values sit in the slots; slot size vs coefficient size     ~1 min
#   TR     the engine trace of Appendix A (no FHE, seconds)
#   E1     which values q0 must hold (intermediate wrap-around)                         ~2 min
#   E1L    at which CKKS level each E1 value lives (reads HEIR's IR in runs/, no FHE)  seconds
#   E2     the W20 Table 2 programs with every column defined                          ~5 min
#   E3     LoopRange vs simple fix / interval / standard affine (no FHE)               ~5 min
#   E4     soundness fuzz (random programs, exact arithmetic)                          ~10 min
#   E5     larger workloads on 1024 slots (+ E5-C raw counts)                          ~30-60 min
#   E6     rolled loops, compile only, needs HEIR101=<venv with heir_py 2026.10.1>/bin  ~15 min
#   GAP    tolerance gap over all real runs                                            seconds
#   BUILD  write every number into report/W22.tex, if that file exists                seconds
#   VERIFY re-check source citations and that report text = data                     seconds
#
# Since 26/10/2026 inputs are rounded to float32 before both the encrypted run and the exact
# reference (heirrun.f32_round), so E1, E2, E5 must be re-run here.
set -u -o pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE/src"
mkdir -p "$HERE/logs" "$HERE/results"
export W22_RUNS="$HERE/runs" W22_GOMOD="$HERE/gomod"
export PATH="$PATH:/usr/local/go/bin"            # non-interactive shells do not read ~/.bashrc
STEPS=${STEPS:-CHECK}
[ "$STEPS" = CHECK ] && STEPS="TOY SLOTS TR E1 E1L E2 GAP BUILD VERIFY"
[ "$STEPS" = FULL ]  && STEPS="TOY SLOTS TR E1 E1L E2 E3 E4 E5 GAP BUILD VERIFY"

echo "== environment =="; date; uname -a
command -v heir-opt >/dev/null || { echo "heir-opt not found: activate the heir_py venv first"; exit 1; }
command -v go >/dev/null || { echo "go not found (expected /usr/local/go/bin/go)"; exit 1; }
heir-opt --version | sed -n 2p; pip show heir_py 2>/dev/null | grep Version
go version; python3 --version; echo "cores: $(nproc)"; free -g | head -2

# provenance: which machine produced each result file (read by build_w22.py)
prov() {  # prov <step> <exit-status>
  python3 - "$1" "$2" <<'PY'
import json, os, sys, socket, datetime
p = os.path.join(os.environ["W22_RUNS"], "..", "results", "provenance.json")
d = json.load(open(p)) if os.path.exists(p) else {}
try: wsl = "microsoft" in open("/proc/version").read().lower()
except OSError: wsl = False
d[sys.argv[1]] = dict(machine="WSL2" if wsl else "other", host=socket.gethostname(), status=int(sys.argv[2]),
                      date=datetime.datetime.now().isoformat(timespec="seconds"))
json.dump(d, open(p, "w"), indent=1)
PY
}
run() {  # run <step> <log-name> <command...>
  local step=$1 log=$2; shift 2
  echo; echo "== $step =="
  "$@" 2>&1 | tee "$HERE/logs/${log}_wsl2.log"
  local st=${PIPESTATUS[0]}
  echo "== $step exit status $st"; prov "$step" "$st"
  STATUS="$STATUS $step:$st"
}
STATUS=""

for s in $STEPS; do
  case $s in
    TOY)   run TOY ckks_toy python3 tools/ckks_toy.py ;;
    SLOTS) python3 -c "import sys; sys.path.insert(0,'looprange3'); import heirrun; heirrun.ensure_gomod()"
           for t in sparsechk coefchk; do mkdir -p "$W22_GOMOD/cmd/$t"; cp "tools/$t.go" "$W22_GOMOD/cmd/$t/main.go"; done
           # GOFLAGS=-mod=mod: let go add the go.sum lines for the Lattigo packages these tools import
           run SLOTS slots_coeffs_check bash -c "cd '$W22_GOMOD' && GOFLAGS=-mod=mod go run ./cmd/sparsechk && GOFLAGS=-mod=mod go run ./cmd/coefchk" ;;
    TR)    run TR trace python3 trace_engine.py ../programs/w20_table2/relax.mlir.in ;;
    E1)    run E1 e1_obligation python3 run_e1_obligation.py ;;
    E1L)   run E1L e1_levels python3 e1_levels.py ;;
    E2)    run E2 e2_table python3 run_e2_table.py ;;
    E3)    run E3 e3_methods python3 run_e3_methods.py ;;
    E4)    run E4 e4_fuzz bash -c "cd looprange3 && python3 fuzz.py 1000 2026" ;;
    E5)    run E5 e5_workload python3 run_e5_workload.py
           E5_WORKLOADS=ema_raw E5_SUFFIX=_raw E5_NS="2 4 8 12" run E5C e5c_raw python3 run_e5_workload.py ;;
    E6)    [ -n "${HEIR101:-}" ] || { echo "E6 skipped: set HEIR101=<venv with heir_py 2026.10.1>/bin"; continue; }
           run E6 e6_rolled python3 run_e6_rolled.py ;;
    GAP)   run GAP threshold_gap python3 threshold_gap.py ;;
    BUILD) [ -f "$HERE/report/W22.tex" ] || { echo "BUILD skipped: report/W22.tex not present"; continue; }
           run BUILD build python3 report_build/build_w22.py ../report/W22.tex --source provenance ;;
    VERIFY) run VERIFY verify_claims python3 verify_claims.py ;;
    *)     echo "unknown step $s" ;;
  esac
done
echo; echo "== summary (step:exit status) ==$STATUS"
grep -h "\[FAIL\]" "$HERE"/logs/ckks_toy_wsl2.log "$HERE"/logs/slots_coeffs_check_wsl2.log "$HERE"/logs/verify_claims_wsl2.log 2>/dev/null && echo "some checks FAILED (see above)" || echo "no FAIL lines in TOY/SLOTS/VERIFY logs"
echo "Results: results/*.json, logs/*.log, runs/<name>/"
