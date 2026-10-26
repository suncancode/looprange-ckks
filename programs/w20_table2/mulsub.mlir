// Test 3 (with a multiplication): y = 0.5 - 64 * x
func.func @f(%x: f32 {secret.secret}) -> f32 {
  %c64 = arith.constant 64.0 : f32
  %half = arith.constant 0.5 : f32
  %m = arith.mulf %x, %c64 : f32
  %y = arith.subf %half, %m : f32
  return %y : f32
}
