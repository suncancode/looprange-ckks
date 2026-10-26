// E1-W3: repeat 8 times: x <- 0.5 - ((x + 512) - 512).  No multiplication, so every value
// stays at level 0; every iteration passes through x + 512, the carried value stays in [-0.5, 1.5].
func.func @f(%x: f32 {secret.secret}) -> f32 {
  %r = affine.for %i = 0 to 8 iter_args(%u = %x) -> (f32) {
    %c = arith.constant 512.0 : f32
    %h = arith.constant 0.5 : f32
    %t = arith.addf %u, %c : f32
    %s = arith.subf %t, %c : f32
    %y = arith.subf %h, %s : f32
    affine.yield %y : f32
  }
  return %r : f32
}
