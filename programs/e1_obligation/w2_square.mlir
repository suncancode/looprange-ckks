// E1-W2: y = (x + 64)(x - 64) + 4096 = x^2.  Intermediate p = x^2 - 4096 (|p| up to 4096)
// is produced by a ciphertext multiplication followed by a rescale.
func.func @f(%x: f32 {secret.secret}) -> f32 {
  %c = arith.constant 64.0 : f32
  %d = arith.constant 4096.0 : f32
  %a = arith.addf %x, %c : f32
  %b = arith.subf %x, %c : f32
  %p = arith.mulf %a, %b : f32
  %y = arith.addf %p, %d : f32
  return %y : f32
}
