#include "cim_sw.h"

// RV32IM scalar baseline. The packed W layout has eight consecutive weights
// per input channel; keep their eight sums live and load each input byte once.
__attribute__((optimize("O3")))
void cim_sw_pointwise(unsigned m, const uint8_t *restrict input,
                      const int8_t *restrict weights, const int32_t *restrict params,
                      uint32_t *restrict output) {
    for (unsigned tile = 0; tile < 8; ++tile) {
        const int8_t *tile_weights = weights + tile * 512;
        const int32_t *tile_params = params + tile * 24;
        for (unsigned p = 0; p < m; ++p) {
            int32_t sums[8];
            #pragma GCC unroll 8
            for (unsigned lane = 0; lane < 8; ++lane)
                sums[lane] = tile_params[3 * lane];
            const uint8_t *row = input + p * 64;
            for (unsigned k = 0; k < 64; ++k) {
                int32_t u = row[k] ^ 128;
                const int8_t *w = tile_weights + k * 8;
                #pragma GCC unroll 8
                for (unsigned lane = 0; lane < 8; ++lane)
                    sums[lane] += u * w[lane];
            }
            uint32_t words[2] = {0, 0};
            #pragma GCC unroll 8
            for (unsigned lane = 0; lane < 8; ++lane) {
                uint32_t byte = cim_sw_requantize(sums[lane], tile_params + 3 * lane);
                words[lane >> 2] |= byte << (8 * (lane & 3));
            }
            output[16 * p + 2 * tile] = words[0];
            output[16 * p + 2 * tile + 1] = words[1];
        }
    }
}
