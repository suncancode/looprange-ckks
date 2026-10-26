// E1-C1 (control): y = (x + 1000) - 990.  Now the OUTPUT is about 10, beyond a 47-bit q0.
func.func @f(%x: f32 {secret.secret}) -> f32 {
  %c = arith.constant 1000.0 : f32
  %d = arith.constant 990.0 : f32
  %t = arith.addf %x, %c : f32
  %y = arith.subf %t, %d : f32
  return %y : f32
}
