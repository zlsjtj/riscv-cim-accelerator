// Test wrapper around the actual pinned gemmlowp scalar primitives.
// gemmlowp commit is TensorFlow v2.16.1 third_party/gemmlowp/workspace.bzl.
#include <cstdint>
#include <cassert>
#include <cmath>
#include <limits>
#include <iostream>
#include "fixedpoint/fixedpoint.h"
#define TFLITE_SINGLE_ROUNDING 0
#define TFLITE_CHECK(x) assert(x)
#define TFLITE_CHECK_LE(x,y) assert((x)<=(y))
#define TfLiteRound std::round
namespace tflite {
#include "official_quantization.inc"
}
int main() {
  int32_t x, m; int s; char kind;
  while (std::cin >> kind) {
    if(kind=='Q') {
      double scale;std::cin>>scale;
      tflite::QuantizeMultiplier(scale,&m,&s);
      std::cout<<m<<' '<<s<<'\n';continue;
    }
    std::cin>>x>>m>>s;
    // TF 2.16.1 common.cc TFLITE_SINGLE_ROUNDING=0, int32 overload,
    // restricted to the documented nonpositive-shift hardware domain.
    std::cout << tflite::MultiplyByQuantizedMultiplier(x,m,s) << '\n';
  }
}
