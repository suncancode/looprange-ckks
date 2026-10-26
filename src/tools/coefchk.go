// coefchk: slot size versus coefficient size (Lattigo v6.2.0), for the 16-value vectors of E1-W4.
//
// Why: decryption reduces the COEFFICIENTS of the plaintext polynomial modulo q, not the slots.
// Every coefficient is bounded by Delta * max|slot|; this tool shows by how much, for the
// input vectors that failed (constant +-1) and passed (alternating +-1) in E1 at 46 bits.
//
// Input : four 16-slot vectors (all +1, all -1, alternating -1/+1, all 0.3), scale Delta = 2^45.
// Output: max|coefficient| / Delta for each; expected 1, 1, 1/sqrt(2) = 0.7071, 0.3.
// Each check prints [PASS] or [FAIL]; the exit status is 1 if any check fails.
package main

import (
	"fmt"
	"math"
	"math/big"
	"os"

	"github.com/tuneinsight/lattigo/v6/core/rlwe"
	"github.com/tuneinsight/lattigo/v6/ring"
	"github.com/tuneinsight/lattigo/v6/schemes/ckks"
)

func main() {
	params, err := ckks.NewParametersFromLiteral(ckks.ParametersLiteral{LogN: 12, LogQ: []int{55, 45}, LogP: []int{61}, LogDefaultScale: 45})
	if err != nil { panic(err) }
	enc := ckks.NewEncoder(params)
	r := params.RingQ().AtLevel(1)
	q := new(big.Int).SetUint64(params.Q()[0])
	q.Mul(q, new(big.Int).SetUint64(params.Q()[1]))
	half := new(big.Int).Rsh(q, 1)
	delta := math.Pow(2, 45)

	vec := func(f func(i int) float64) []float64 {
		v := make([]float64, 16)
		for i := range v { v[i] = f(i) }
		return v
	}
	cases := []struct {
		name string
		v    []float64
		want float64
	}{
		{"all +1", vec(func(int) float64 { return 1 }), 1},
		{"all -1", vec(func(int) float64 { return -1 }), 1},
		{"alternating -1,+1", vec(func(i int) float64 { return float64(2*(i%2) - 1) }), 1 / math.Sqrt2},
		{"all 0.3", vec(func(int) float64 { return 0.3 }), 0.3},
	}
	fails := 0
	for _, c := range cases {
		pt := ckks.NewPlaintext(params, 1)
		pt.LogDimensions = ring.Dimensions{Rows: 0, Cols: 4}          // 16 slots
		pt.Scale = rlwe.NewScale(delta)
		if err := enc.Encode(c.v, pt); err != nil { panic(err) }
		p := *pt.Value.CopyNew()
		if pt.IsNTT { r.INTT(p, p) }
		if pt.IsMontgomery { r.IMForm(p, p) }
		cs := make([]*big.Int, params.N())
		for i := range cs { cs[i] = new(big.Int) }
		r.PolyToBigint(p, 1, cs)
		maxc, nz := 0.0, 0
		for _, x := range cs {
			if x.Cmp(half) >= 0 { x.Sub(x, q) }                       // centred representative
			f, _ := new(big.Float).SetInt(x).Float64()
			if f != 0 { nz++ }
			maxc = math.Max(maxc, math.Abs(f))
		}
		ok := math.Abs(maxc/delta-c.want) < 1e-3
		if !ok { fails++ }
		s := map[bool]string{true: "PASS", false: "FAIL"}[ok]
		fmt.Printf("  [%s] %-18s max|slot| = %.1f  max|coefficient|/Delta = %.4f (expected %.4f), non-zero coefficients = %d\n",
			s, c.name, math.Abs(c.v[0]), maxc/delta, c.want, nz)
	}
	fmt.Printf("%d check(s) failed\n", fails)
	if fails > 0 { os.Exit(1) }
}
