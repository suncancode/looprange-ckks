// E1-W1: y = (x + 1000) - 1000.  Intermediate t = x + 1000 reaches 1001; the output is x.
func.func @f(%x: f32 {secret.secret}) -> f32 {
  %c = arith.constant 1000.0 : f32
  %t = arith.addf %x, %c : f32
  %y = arith.subf %t, %c : f32
  return %y : f32
}
