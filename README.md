# LoopRange

**Sound value bounds for CKKS programs with loops.**

In CKKS, a real value `y` is stored as an integer polynomial scaled by `Δ` and is decrypted modulo
the current modulus. If `Δ·|y|` reaches half the modulus, the decrypted value wraps around and is
wrong. A compiler therefore has to choose the first modulus `q0` from a bound on `|y|`.

LoopRange computes such a bound for the programs that the [HEIR](https://github.com/google/heir)
compiler compiles, and passes it to HEIR as a number of bits:

```
q0 bits = 45 + ceil(log2 B) + 2        (scale Δ = 2^45; the same rule as HEIR's GenerateParamCKKS)
```

- **Input:** the same `.mlir` file that HEIR compiles (`arith` operations, `tensor_ext.rotate`, `affine.for` loops).
- **Analysis:** affine forms over exact rationals, with symbols that carry a slot shift so that rotations are tracked exactly, plus a loop engine that proves an inductive invariant. The bound is sound for a static or a dynamic (unknown but public) trip count, and the engine always stops; when no invariant is found, the answer is *bound not established*.
- **Output:** `B` for the returned values (OUT) and for every value (ALL), and the bits of `q0`, passed to HEIR through `--mlir-to-ckks="first-mod-bits=<q0>"`. HEIR itself is not modified.

Only decrypted values need to fit in the modulus: in a leveled circuit, intermediate values may wrap around and the output is still correct (experiment E1).

## Install

```bash
git clone https://github.com/suncancode/looprange-ckks && cd looprange-ckks
python3 -m pip install pytest                      # LoopRange itself needs only the standard library
python3 -m pytest -q tests                         # 7 tests, a few seconds
```

The end-to-end experiments also need `heir_py==2026.9.1` (`pip install -r requirements.txt`) and Go >= 1.23 on the `PATH` or at `/usr/local/go/bin`; Lattigo v6.2.0 is downloaded by `go` on the first build. They were run on Ubuntu (WSL2).

## Usage

Bounds and `q0` of one program, for every method:

```bash
python3 src/looprange3/cli.py programs/e1_obligation/w3_loop.mlir
```
```
Q0 heir-impl OUT=46 ALL=57 STATUS=bounded       <- model of HEIR's analysis: 46 bits is too small (E1)
Q0 simple-fix OUT=61 ALL=61 STATUS=bounded
Q0 interval OUT=47 ALL=57 STATUS=bounded
...
Q0 looprange OUT=47 ALL=57 STATUS=bounded
```

Input ranges default to `[-1, 1]` (as in HEIR); another range is declared in the `.mlir` file with a comment `// range %x = [-2048, 2048]`, or on the command line with `--range x=-2048:2048`.

Compile and run with HEIR + Lattigo and compare with the exact result (`src/heirrun.py`):

```bash
cd src
echo '[{"x": 1.0}, {"x": -1.0}, {"x": 0.3}]' > /tmp/inputs.json
python3 heirrun.py ../programs/e1_obligation/w1_shift.mlir --fmb 47 --inputs /tmp/inputs.json --out ../runs/w1_47
# RESULT {... "status": "OK", "max_err": ..., "params": {"logN": ..., "Q_bits": [...]} ...}
```
`--fmb 0` lets HEIR choose `q0` with its own analysis; `--fmb default` uses HEIR's default of 55 bits.

## Experiments

`run_w22_wsl2.sh` runs any list of steps and writes `results/*.json`, `logs/*.log` and, for every compiled program, the HEIR output, the generated Go code and the driver in `runs/<name>/`.

```bash
bash run_w22_wsl2.sh                      # TOY SLOTS TR E1 E1L E2 GAP BUILD VERIFY  (~10 min)
STEPS=FULL bash run_w22_wsl2.sh           # + E3 E4 E5                               (~1 h)
STEPS="E3 E4" bash run_w22_wsl2.sh        # any list
```

| Step | Script | Question |
|---|---|---|
| TOY | `src/tools/ckks_toy.py` | hand-sized CKKS examples: encode, encrypt, decrypt, decode, wrap-around |
| SLOTS | `src/tools/sparsechk.go`, `coefchk.go` | how Lattigo places 1024 values in the slots; slot size vs coefficient size |
| E1 | `src/run_e1_obligation.py` | must `q0` hold intermediate values, or only decrypted ones? |
| E1L | `src/e1_levels.py` | at which CKKS level does each E1 value live? |
| E2 | `src/run_e2_table.py` | are the results correct end to end, for each method's `q0`? |
| E3 | `src/run_e3_methods.py` | LoopRange vs simple fix, signed intervals, standard affine arithmetic (10 kernels) |
| E4 | `src/looprange3/fuzz.py` | soundness on 1000 random programs, exact arithmetic |
| E5 | `src/run_e5_workload.py` | larger workloads on 1024 slots: runtime and memory |
| E6 | `src/run_e6_rolled.py` | rolled loops with HEIR 2026.10.1 (compile only; set `HEIR101=<venv>/bin`) |
| TR | `src/trace_engine.py` | step-by-step trace of the loop engine |
| GAP | `src/threshold_gap.py` | does the result depend on the error tolerance? |
| VERIFY | `src/verify_claims.py` | re-checks cited source lines (Lattigo, HEIR) and recomputes the reported numbers |

**Definitions used by every experiment**

- *Correct*: `|decrypted - exact| <= 1e-3 * max(1, |exact|)` in every slot, for every input set; the exact result is computed in rational arithmetic (`src/looprange3/concrete.py`).
- *Smallest passing size*: the smallest `first-mod-bits`, from 45 up, for which all our input sets are correct. It is a test result, not a proven minimum.
- *Bound not established*: no inductive box was found within the engine's limits. It does not mean that the values are unbounded.
- HEIR errors, build errors and run errors have their own statuses (REFUSED, TRANSLATE-FAIL, BUILD-FAIL, RUN-FAIL) and are never counted as correct or wrong.

## Repository layout

```
src/looprange3/     LoopRange
  ir.py               program model (operations, loops)
  mlir_reader.py      reads the .mlir file; any unsupported line is an error
  domains.py          HEIR-as-implemented, simple fix, signed interval, affine forms (AA)
  analysis.py         loop engine, stopping rule, OUT/ALL bounds, METHODS
  concrete.py         exact reference semantics (Fractions)
  cli.py, fuzz.py     command line; soundness fuzzer
src/heirrun.py      HEIR -> Go/Lattigo -> run -> compare
src/exp_common.py   input sets, bounds of every method, smallest passing size
src/run_e*.py       experiments (see the table above)
src/tools/          CKKS toy example; Lattigo slot and coefficient checks
src/report_build/   writes the report's numbers from results/*.json
programs/           every MLIR input (*.mlir.in are templates; @N@ = trip count, ? = dynamic)
tests/              tests without any FHE library (run on every push)
```

## Limitations

- Supported: `addf`, `subf`, `mulf`, `negf`, rotations by a constant or by the loop index, scalar and per-slot constants, loops placed one after another. Not supported: division, comparisons, approximated functions, nested loops.
- The CKKS error is measured, not bounded; a bound on the value is one of several conditions for a correct encrypted run.
- Per-slot weight vectors (kernel `k10`) give loose bounds.
- Bootstrapping inputs are not analysed yet.

## License

MIT, see [LICENSE](LICENSE). HEIR and Lattigo are separate projects under their own licenses and are not included here.
