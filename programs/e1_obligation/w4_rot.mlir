// E1-W4 (vector, rotation): y = rot((x + 1000), 1) - 1000 = rot(x, 1).
func.func @f(%x: tensor<16xf32> {secret.secret}) -> tensor<16xf32> {
  %c = arith.constant dense<1000.0> : tensor<16xf32>
  %k = arith.constant 1 : index
  %t = arith.addf %x, %c : tensor<16xf32>
  %r = tensor_ext.rotate %t, %k : tensor<16xf32>, index
  %y = arith.subf %r, %c : tensor<16xf32>
  return %y : tensor<16xf32>
}
