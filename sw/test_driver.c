#include "cim.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>

static int8_t weights[64][64];
static cim_param params[64];
static uint8_t packed_w[4096], packed_p[768];

int main(void) {
    cim_task t = {125, 0x1000, 0x4000, 0x6000, 0x8000, 1};
    unsigned o, i;
    const int8_t (*view)[64] = (const int8_t (*)[64])weights;
    for (o = 0; o < 64; ++o) {
        params[o].bias = -(int32_t)o;
        params[o].multiplier = 1234567890;
        params[o].shift = -8;
        for (i = 0; i < 64; ++i)
            weights[o][i] = (int8_t)((int)((o*31+i*7) % 256) - 128);
    }
    assert(cim_validate(&t, view, params) == CIM_OK);
    cim_pack_weights(packed_w, view);
    for (o = 0; o < 64; ++o)
        for (i = 0; i < 64; ++i)
            assert(packed_w[512*(o/8)+8*i+o%8] == (uint8_t)weights[o][i]);
    cim_pack_params(packed_p, params);
    assert(packed_p[12+0] == 255 && packed_p[12+3] == 255);
    assert(packed_p[8] == 248 && packed_p[11] == 255);
    t.m = 0; assert(cim_validate(&t, view, params) == CIM_EINVAL); t.m = 125;
    t.y_base = t.a_base; assert(cim_validate(&t, view, params) == CIM_EINVAL);
    t.y_base = 0xfffffffc; assert(cim_validate(&t, view, params) == CIM_EINVAL);
    t.y_base = 0x8001; assert(cim_validate(&t, view, params) == CIM_EINVAL);
    t.y_base = 0x8000;
    params[0].shift = 1; assert(cim_validate(&t, view, params) == CIM_EINVAL);
    params[0].shift = -8; params[0].bias = INT32_MAX;
    assert(cim_validate(&t, view, params) == CIM_EINVAL);
    puts("PASS host C driver: packing, parameter/range/overflow checks");
    return 0;
}
