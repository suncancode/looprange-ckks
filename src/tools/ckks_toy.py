"""ckks_toy.py -- the hand-sized CKKS examples used in the explanations, recomputed from scratch.

Pure Python (no numpy).  Follows the textbook CKKS algorithms of Cheon-Kim-Kim-Song,
ePrint 2016/421, Sec. 3.4 (pp. 11-12): Encode, KeyGen, Encrypt, Decrypt, Decode, Add.
Every printed number can be checked by hand.  Each check ends with PASS/FAIL.

    python3 ckks_toy.py
"""
import cmath, math
from decimal import Decimal, getcontext

fails = 0


def check(name, ok):
    global fails
    fails += (not ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")


# ---------------------------------------------------------------- ring helpers (R = Z[X]/(X^N+1))
def mul(a, b, N):
    p = [0] * (2 * N)
    for i in range(N):
        for j in range(N):
            p[i + j] += a[i] * b[j]
    return [p[k] - p[k + N] for k in range(N)]          # X^N = -1


def add(*vs): return [sum(t) for t in zip(*vs)]
def mod(v, q): return [x % q for x in v]
def centre(v, q): return [x - q if x > q // 2 else x for x in mod(v, q)]


def slot_exponents(N):
    M = 2 * N
    return [pow(5, k, M) for k in range(N // 2)]        # slots at zeta^(5^k)


def encode(z, N, delta):
    """m = round(delta * z(X)), z(X) the real polynomial with z(zeta^j) = z_j for j in S
    (and the conjugates at -j).  Closed form: c_k = (1/N) sum_j v_j zeta^(-j k)."""
    M = 2 * N; zeta = cmath.exp(2j * math.pi / M)
    S = slot_exponents(N)
    pts = S + [(-j) % M for j in S]
    vals = list(z) + [complex(x).conjugate() for x in z]
    coef = [sum(vals[i] * zeta ** (-pts[i] * k) for i in range(N)).real / N for k in range(N)]
    return coef, [round(delta * c) for c in coef]


def decode(m, N, delta):
    M = 2 * N; zeta = cmath.exp(2j * math.pi / M)
    return [sum(m[k] * zeta ** (j * k) for k in range(N)) / delta for j in slot_exponents(N)]


print("== 1. Full textbook example: N=4 (2 slots), Delta=64, q=40961, z=(0.5,-0.25) ==")
N, D, q = 4, 64, 40961
zc, m = encode([0.5, -0.25], N, D)
print("  z(X) coefficients:", [round(c, 5) for c in zc])
print("  Encode: m = round(64 z(X)) =", m)
check("m = (8, 17, 0, -17)", m == [8, 17, 0, -17])
s = [1, 0, -1, 0]                       # s <- HWT(2): s = 1 - X^2
a = [31415, 9265, 35897, 23846]         # a <- U_q
e = [1, 0, -2, 1]                       # e <- DG
as_ = mul(a, s, N)
b = mod(add([-x for x in as_], e), q)
print("  KeyGen: a*s =", as_, " b = -a*s + e mod q =", b)
check("a*s = (67312, 33111, 4482, 14581)", as_ == [67312, 33111, 4482, 14581])
check("pk b = (14611, 7850, 36477, 26381)", b == [14611, 7850, 36477, 26381])
v = [1, 0, 0, -1]                       # v <- ZO(0.5): v = 1 - X^3
e0, e1 = [0, 1, -1, 0], [1, -1, 0, 0]
c0 = mod(add(mul(v, b, N), m, e0), q)
c1 = mod(add(mul(v, a, N), e1), q)
print("  Encrypt: c0 = v*b + m + e0 =", c0, "  c1 = v*a + e1 =", c1)
check("c0 = (22469, 3384, 21896, 11753)", c0 == [22469, 3384, 21896, 11753])
check("c1 = (40681, 4200, 18782, 33392)", c1 == [40681, 4200, 18782, 33392])
dec = centre(add(c0, mul(c1, s, N)), q)
noise = add(mul(v, e, N), e0, mul(e1, s, N))
print("  Decrypt: c0 + c1*s mod q, centred =", dec, "  total noise v*e+e0+e1*s =", noise)
check("decryption = m + noise = (10, 15, -3, -16)", dec == add(m, noise) == [10, 15, -3, -16])
z_out = decode(dec, N, D)
print("  Decode:", [complex(round(x.real, 4), round(x.imag, 4)) for x in z_out])
bound = sum(abs(x) for x in noise) / D + sum(abs(x) for x in add(m, [-round(D * c) for c in zc])) / D + 1e-3
err = max(abs(z_out[0] - 0.5), abs(z_out[1] + 0.25))
print(f"  largest decode error {err:.4f} <= sum|noise coefficients|/Delta (+ encoding rounding) = {bound:.4f}")
check("decode error is within the noise bound sum|noise_k|/Delta", err <= bound)
d2 = centre(add(mod([2 * x for x in c0], q), mul(mod([2 * x for x in c1], q), s, N)), q)
print("  Add (ct+ct) decrypts to", d2, "-> decode", [round(x.real, 3) for x in decode(d2, N, D)])
check("ct+ct = 2*(m+noise)", d2 == [2 * x for x in dec])

print("\n== 2. Array [3, 10] with Delta = 2^45 (N=4) ==")
getcontext().prec = 60
DD = Decimal(2) ** 45; r2 = Decimal(2).sqrt()
c_exact = [(Decimal(3) + 10) / 2, (Decimal(3) - 10) * r2 / 4, Decimal(0), -(Decimal(3) - 10) * r2 / 4]
m2 = [int((c * DD).to_integral_value()) for c in c_exact]
print("  z(X) =", [str(round(c, 6)) for c in c_exact])
print("  stored coefficients m =", m2)
check("m = (228698418577408, -87076878335313, 0, 87076878335313)",
      m2 == [228698418577408, -87076878335313, 0, 87076878335313])
z2 = decode(m2, 4, 2.0 ** 45)
print("  decode:", [round(x.real, 12) for x in z2])
check("decode = (3, 10) to 1e-12", abs(z2[0] - 3) < 1e-12 and abs(z2[1] - 10) < 1e-12)
print(f"  q0 rule with B=10: {45 + math.ceil(math.log2(10)) + 2} bits; largest coefficient / Delta = {max(abs(x) for x in m2) / 2**45}")

print("\n== 3. Eight numbers, N=16 (8 slots), Delta = 2^45 ==")
z8 = [3, 10, -2, 7, 0.5, 4, -8, 1]
c8, m8 = encode(z8, 16, 2.0 ** 45)
print("  slot points zeta^j, j =", slot_exponents(16))
print("  z(X) coefficients:", [round(c, 4) for c in c8])
d8 = decode(m8, 16, 2.0 ** 45)
check("decode returns the 8 numbers to 1e-9", max(abs(d8[i] - z8[i]) for i in range(8)) < 1e-9)
check("c0 = mean of the slots (1.9375)", abs(c8[0] - sum(z8) / 8) < 1e-12)
check("every |coefficient| <= max|slot|", max(abs(c) for c in c8) <= max(abs(x) for x in z8) + 1e-12)

print("\n== 4. Wrap-around happens on coefficients: q=101 (range -50..50), Delta=64, N=4 ==")
for z in ([1, 1], [1, -1]):
    _, mz = encode(z, 4, 64)
    cz = centre(mz, 101)
    out = [round(x.real, 3) for x in decode(cz, 4, 64)]
    print(f"  z={z}: coefficients {mz} -> centred mod 101 {cz} -> decode {out}")
_, m11 = encode([1, 1], 4, 64); _, m1m = encode([1, -1], 4, 64)
check("(1,1): coefficient 64 > 50 wraps, both slots wrong", centre(m11, 101)[0] == -37)
check("(1,-1): coefficients +-45 stay inside, decodes correctly", centre(m1m, 101) == m1m)

print("\n== 5. An intermediate value may wrap; only the decrypted one matters (Delta=10, q=101) ==")
x = 3                                   # 0.3 * 10
mid = (x + 10000) % 101                 # x + 1000 in message units
end = (mid - 10000) % 101
mid_c, end_c = (mid - 101 if mid > 50 else mid), (end - 101 if end > 50 else end)
print(f"  x=0.3 -> 3; x+1000 -> 10003 mod 101 = {mid_c} (decrypting here gives {mid_c/10}, wrong);"
      f" (x+1000)-1000 -> {end_c} -> {end_c/10} (right)")
check("intermediate wraps (would decode 0.4)", mid_c == 4)
check("final value correct (0.3)", end_c == 3)

print(f"\n{fails} check(s) failed")
