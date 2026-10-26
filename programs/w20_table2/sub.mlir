// Test 1b: y = x - z
func.func @f(%x: f32 {secret.secret}, %z: f32 {secret.secret}) -> f32 {
  %y = arith.subf %x, %z : f32
  return %y : f32
}
