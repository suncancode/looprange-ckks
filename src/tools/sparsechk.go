// sparsechk: how does Lattigo (v6.2.0) place a 1024-value vector in a ring with more slots?
// This is what HEIR's generated code does (pt.LogDimensions = {Rows: 0, Cols: 10}).
//
// Input : a 1024-value vector v[i] = (i mod 7) - 3, scale 2^45, and the all-ones vector.
// Output: for logN = 12 (2048 slots) and logN = 15 (16384 slots, as in HEIR's heat code):
//   (1) which polynomial coefficients are non-zero (expected: only every (N/2048)-th one),
//   (2) the plaintext decoded as a full-slot vector (expected: v repeated N/2048 times),
//   (3) the all-ones vector (expected: the constant polynomial 2^45, all other coefficients 0).
// Each check prints [PASS] or [FAIL]; the exit status is 1 if any check fails.
package main

import (
	"fmt"
	"math"
	"os"

	"github.com/tuneinsight/lattigo/v6/core/rlwe"
	"github.com/tuneinsight/lattigo/v6/ring"
	"github.com/tuneinsight/lattigo/v6/schemes/ckks"
)

var fails = 0

func check(name string, ok bool) {
	s := "PASS"
	if !ok { s = "FAIL"; fails++ }
	fmt.Printf("  [%s] %s\n", s, name)
}

// coefficients of a plaintext (undo NTT / Montgomery form if the encoder used them)
func coeffs(params ckks.Parameters, pt *rlwe.Plaintext) ring.Poly {
	r := params.RingQ().AtLevel(pt.Level())
	p := *pt.Value.CopyNew()
	if pt.IsNTT { r.INTT(p, p) }
	if pt.IsMontgomery { r.IMForm(p, p) }
	return p
}

func main() {
	for _, logN := range []int{12, 15} {
		params, err := ckks.NewParametersFromLiteral(ckks.ParametersLiteral{LogN: logN, LogQ: []int{55, 45}, LogP: []int{61}, LogDefaultScale: 45})
		if err != nil { panic(err) }
		enc := ckks.NewEncoder(params)
		gap := params.N() / 2048                       // 1024 complex slots use every gap-th coefficient
		fmt.Printf("logN=%d: N=%d coefficients, %d slots in the ring, vector of 1024 -> expected gap %d\n",
			logN, params.N(), params.MaxSlots(), gap)

		v := make([]float64, 1024)
		for i := range v { v[i] = float64(i%7) - 3 }
		pt := ckks.NewPlaintext(params, 1)
		pt.LogDimensions = ring.Dimensions{Rows: 0, Cols: 10}
		pt.Scale = rlwe.NewScale(math.Pow(2, 45))
		if err := enc.Encode(v, pt); err != nil { panic(err) }
		p := coeffs(params, pt)
		nz, off := 0, 0
		for j := 0; j < params.N(); j++ {
			if p.Coeffs[0][j] != 0 { nz++; if j%gap != 0 { off++ } }
		}
		fmt.Printf("  non-zero coefficients: %d, of which not at a multiple of %d: %d\n", nz, gap, off)
		check("non-zero coefficients only at multiples of the gap", off == 0)

		full := make([]float64, params.MaxSlots())
		ptFull := *pt
		ptFull.LogDimensions = ring.Dimensions{Rows: 0, Cols: params.LogMaxSlots()}
		if err := enc.Decode(&ptFull, full); err != nil { panic(err) }
		maxd := 0.0
		for i := range full { maxd = math.Max(maxd, math.Abs(full[i]-v[i%1024])) }
		fmt.Printf("  decoded as %d slots: max |slot[i] - v[i mod 1024]| = %.2e\n", len(full), maxd)
		check("the 1024 values are repeated to fill every slot", maxd < 1e-9)

		ones := make([]float64, 1024)
		for i := range ones { ones[i] = 1 }
		pt1 := ckks.NewPlaintext(params, 1)
		pt1.LogDimensions = ring.Dimensions{Rows: 0, Cols: 10}
		pt1.Scale = rlwe.NewScale(math.Pow(2, 45))
		if err := enc.Encode(ones, pt1); err != nil { panic(err) }
		q := coeffs(params, pt1)
		others := 0
		for j := 1; j < params.N(); j++ { if q.Coeffs[0][j] != 0 { others++ } }
		fmt.Printf("  all-ones vector: coefficient 0 = %d (2^45 = %d), other non-zero coefficients = %d\n",
			q.Coeffs[0][0], uint64(1)<<45, others)
		check("all-ones vector = the constant polynomial 2^45", q.Coeffs[0][0] == uint64(1)<<45 && others == 0)
	}
	fmt.Printf("%d check(s) failed\n", fails)
	if fails > 0 { os.Exit(1) }
}
