// SPDX-License-Identifier: Apache-2.0
#ifndef CIM_SW_H
#define CIM_SW_H

#include <stdint.h>

void cim_sw_pointwise(unsigned m, const uint8_t *restrict input,
                      const int8_t *restrict weights, const int32_t *restrict params,
                      uint32_t *restrict output);

// INT32 double rounding with shift in [-31, 0], zero point -128 and ReLU.
static inline uint8_t cim_sw_requantize(int32_t acc, const int32_t *params) {
    int64_t product = (int64_t)acc * params[1];
    int64_t nudged = product + (product >= 0 ? INT64_C(1073741824) : -INT64_C(1073741823));
    // Convert the signed arithmetic shift to division truncated toward zero.
    int32_t high = (int32_t)((nudged + (nudged < 0 ? INT64_C(2147483647) : 0)) >> 31);
    unsigned exponent = (unsigned)-params[2];
    uint32_t mask = (UINT32_C(1) << exponent) - 1;
    uint32_t remainder = (uint32_t)high & mask;
    uint32_t threshold = (mask >> 1) + (high < 0);
    int32_t rounded = (high >> exponent) + (remainder > threshold);
    if (rounded < 0) return UINT8_C(128);
    if (rounded > 255) return UINT8_C(127);
    return (uint8_t)(rounded - 128);
}
#endif
