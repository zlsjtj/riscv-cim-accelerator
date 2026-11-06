#include "cim.h"
#include <limits.h>

static int ranges_valid(const cim_task *t) {
    uint64_t base[4], end[4];
    unsigned i, j;
    if (!t || t->m < 1 || t->m > 125 || t->mode > 1) return 0;
    base[0] = t->a_base; base[1] = t->w_base;
    base[2] = t->p_base; base[3] = t->y_base;
    end[0] = base[0] + 64u * t->m; end[1] = base[1] + 4096u;
    end[2] = base[2] + 768u; end[3] = base[3] + 64u * t->m;
    for (i = 0; i < 4; ++i) {
        if ((base[i] & 3u) || end[i] > UINT64_C(0x100000000)) return 0;
        for (j = 0; j < i; ++j)
            if (base[i] < end[j] && base[j] < end[i]) return 0;
    }
    return 1;
}

int cim_validate(const cim_task *t, const int8_t w[64][64],
                 const cim_param p[64]) {
    unsigned o, i;
    if (!ranges_valid(t) || !w || !p) return CIM_EINVAL;
    for (o = 0; o < 64; ++o) {
        int64_t lo = p[o].bias, hi = p[o].bias;
        if (p[o].shift < -31 || p[o].shift > 0 || p[o].multiplier < 0)
            return CIM_EINVAL;
        for (i = 0; i < 64; ++i) {
            int64_t contribution = 255 * (int64_t)w[o][i];
            if (contribution < 0) lo += contribution;
            else hi += contribution;
        }
        if (lo < INT32_MIN || hi > INT32_MAX) return CIM_EINVAL;
    }
    return CIM_OK;
}

void cim_pack_weights(uint8_t packed[4096], const int8_t w[64][64]) {
    unsigned t, i, j;
    for (t = 0; t < 8; ++t)
        for (i = 0; i < 64; ++i)
            for (j = 0; j < 8; ++j)
                packed[512*t + 8*i + j] = (uint8_t)w[8*t+j][i];
}

static void put_le32(uint8_t *p, int32_t value) {
    uint32_t u = (uint32_t)value;
    unsigned i;
    for (i = 0; i < 4; ++i) p[i] = (uint8_t)(u >> (8*i));
}

void cim_pack_params(uint8_t packed[768], const cim_param p[64]) {
    unsigned o;
    for (o = 0; o < 64; ++o) {
        put_le32(packed + 12*o, p[o].bias);
        put_le32(packed + 12*o + 4, p[o].multiplier);
        put_le32(packed + 12*o + 8, p[o].shift);
    }
}

static int device_valid(const cim_device *d) {
    return d && d->read32 && d->write32 && d->prepare && d->acquire;
}

static void write_task(const cim_device *d, const cim_task *t) {
    d->write32(d->context, CIM_M, t->m);
    d->write32(d->context, CIM_A_BASE, t->a_base);
    d->write32(d->context, CIM_W_BASE, t->w_base);
    d->write32(d->context, CIM_P_BASE, t->p_base);
    d->write32(d->context, CIM_Y_BASE, t->y_base);
    d->write32(d->context, CIM_MODE, t->mode);
}

int cim_submit(const cim_device *d, const cim_task *t) {
    if (!device_valid(d) || !ranges_valid(t)) return CIM_EINVAL;
    if (d->read32(d->context, CIM_STATUS) & CIM_BUSY) return CIM_EBUSY;
    write_task(d, t);
    d->prepare(d->context);
    d->write32(d->context, CIM_CONTROL, CIM_START);
    return CIM_OK;
}

int cim_submit_pair_with_options(const cim_device *d, const cim_task *first,
                                 const cim_task *second, uint32_t options) {
    if ((options & ~(uint32_t)(CIM_RETAIN | CIM_PREFETCH | CIM_EARLY_WRITE)) ||
        ((options & CIM_PREFETCH) && !(options & CIM_RETAIN)) || !device_valid(d) ||
        !ranges_valid(first) || !ranges_valid(second) ||
        ((options & CIM_EARLY_WRITE) && (!(options & CIM_PREFETCH) || first->mode != 1)) ||
        first->y_base != second->a_base || first->m != second->m || first->mode != second->mode)
        return CIM_EINVAL;
    if (d->read32(d->context, CIM_STATUS) & CIM_BUSY) return CIM_EBUSY;
    write_task(d, first);
    d->write32(d->context, CIM_W2_BASE, second->w_base);
    d->write32(d->context, CIM_P2_BASE, second->p_base);
    d->write32(d->context, CIM_Y2_BASE, second->y_base);
    d->prepare(d->context);
    d->write32(d->context, CIM_CONTROL, CIM_START | CIM_CHAIN | options);
    return CIM_OK;
}

int cim_submit_pair(const cim_device *d, const cim_task *first, const cim_task *second) {
    return cim_submit_pair_with_options(d, first, second, 0);
}

int cim_wait(const cim_device *d, uint32_t limit, uint32_t *cycles) {
    uint32_t i;
    if (!device_valid(d)) return CIM_EINVAL;
    for (i = 0; i < limit; ++i) {
        uint32_t s = d->read32(d->context, CIM_STATUS);
        if (s & CIM_ERROR) return CIM_EHW;
        if (s & CIM_DONE) {
            d->acquire(d->context);
            if (cycles) *cycles = d->read32(d->context, CIM_CYCLES);
            return CIM_OK;
        }
    }
    return CIM_ETIMEOUT;
}

void cim_ack(const cim_device *d) {
    if (device_valid(d)) d->write32(d->context, CIM_CONTROL, CIM_ACK_DONE);
}
