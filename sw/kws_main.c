// SPDX-License-Identifier: Apache-2.0
// Fixed KWS op2 PW -> op3 DW -> op4 PW, shared by both CPU platforms.
#include "cim.h"
#include "cim_sw.h"

#ifdef KWS_K7
enum {
    DATA_BASE = 0x80100000, CIM_BASE = 0x80201000,
    UART_STATUS = 0x80201100, OUTPUT = 0x80201104, TIMER = 0x80201118
};
#else
enum {
    DATA_BASE = 0x00110000, CIM_BASE = 0x00040000,
    OUTPUT = 0x00020000, SIM_EXIT = 0x00020008, TIMER = 0x00030000
};
#endif

enum {
    A = DATA_BASE + 0x1000, B = DATA_BASE + 0x6000,
    W1 = DATA_BASE + 0x3000, W2 = DATA_BASE + 0x4000,
    P1 = DATA_BASE + 0x5000, P2 = DATA_BASE + 0x5400,
    DW_W = DATA_BASE + 0x5800, DW_P = DATA_BASE + 0x5c00,
    H = 25, WIDTH = 5, CHANNELS = 64, NBYTES = H * WIDTH * CHANNELS, CASES = 2
};

static const cim_task tasks[] = {
    {H * WIDTH, A, W1, P1, B, 1},
    {H * WIDTH, A, W2, P2, B, 1}
};

static inline uint32_t rd(uint32_t address) {
    return *(volatile const uint32_t *)(uintptr_t)address;
}

static inline void wr(uint32_t address, uint32_t value) {
    *(volatile uint32_t *)(uintptr_t)address = value;
}

static uint32_t cfg_read(void *context, uint32_t offset) {
    (void)context;
    return rd(CIM_BASE + offset);
}

static void cfg_write(void *context, uint32_t offset, uint32_t value) {
    (void)context;
    wr(CIM_BASE + offset, value);
}

static void visibility(void *context) {
    (void)context;
#ifdef KWS_K7
    __asm__ volatile ("" ::: "memory"); // The K7 BSP uses uncached ordered SRAM.
#else
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
#endif
}

static const cim_device device = {0, cfg_read, cfg_write, visibility, visibility};

static void put(char c) {
#ifdef KWS_K7
    while (rd(UART_STATUS) & 1u) {}
#endif
    wr(OUTPUT, (uint8_t)c);
}

static void print(const char *s) {
    while (*s) put(*s++);
}

static void hex(uint32_t value, unsigned digits) {
    while (digits) {
        unsigned digit = (value >> (4 * --digits)) & 15u;
        put((char)(digit < 10 ? '0' + digit : 'a' + digit - 10));
    }
}

static void field(uint32_t value) {
    put(' ');
    hex(value, 8);
}

static uint32_t input_base(unsigned sample) {
    return DATA_BASE + 0x8000 + sample * 0x4000;
}

static void restore_input(unsigned sample) {
    uint32_t input = input_base(sample);
    for (uint32_t i = 0; i < NBYTES; i += 4)
        wr(B + i, ~rd(input + 0x2000 + i));
    // Restore A last so recent CPU stores to B cannot shadow PW1 writes.
    for (uint32_t i = 0; i < NBYTES; i += 4)
        wr(A + i, rd(input + i));
    visibility(0);
}

static int pointwise(const cim_task *task, unsigned cpu_only, uint32_t *core) {
    if (cpu_only) {
        cim_sw_pointwise(task->m, (const uint8_t *)(uintptr_t)task->a_base,
                         (const int8_t *)(uintptr_t)task->w_base,
                         (const int32_t *)(uintptr_t)task->p_base,
                         (uint32_t *)(uintptr_t)task->y_base);
        return CIM_OK;
    }
    int status = cim_submit(&device, task);
    return status == CIM_OK ? cim_wait(&device, 100000, core) : status;
}

// Exact op3 shape and SAME padding. A padded sample is zero after the
// input zero-point correction, so out-of-bounds taps are skipped.
__attribute__((optimize("O3"), noinline))
static void depthwise(const uint8_t *restrict input, uint8_t *restrict output,
                      const int8_t *restrict weights, const int32_t *restrict params) {
    for (int y = 0; y < H; ++y) {
        for (int x = 0; x < WIDTH; ++x) {
            for (int ch = 0; ch < CHANNELS; ++ch) {
                int32_t acc = params[3 * ch];
                for (int ky = 0; ky < 3; ++ky) {
                    int iy = y + ky - 1;
                    if (iy < 0 || iy >= H) continue;
                    for (int kx = 0; kx < 3; ++kx) {
                        int ix = x + kx - 1;
                        if (ix < 0 || ix >= WIDTH) continue;
                        int32_t corrected = input[(iy * WIDTH + ix) * CHANNELS + ch] ^ 128;
                        acc += corrected * weights[(ky * 3 + kx) * CHANNELS + ch];
                    }
                }
                output[(y * WIDTH + x) * CHANNELS + ch] = cim_sw_requantize(acc, params + 3 * ch);
            }
        }
    }
}

static void run_dw(void) {
    depthwise((const uint8_t *)(uintptr_t)B, (uint8_t *)(uintptr_t)A,
              (const int8_t *)(uintptr_t)DW_W, (const int32_t *)(uintptr_t)DW_P);
}

static unsigned compare_final(unsigned sample) {
    uint32_t golden = input_base(sample) + 0x2000;
    unsigned bad = 0;
    for (uint32_t i = 0; i < NBYTES; i += 4) {
        uint32_t diff = rd(B + i) ^ rd(golden + i);
        for (unsigned lane = 0; lane < 4; ++lane)
            bad += ((diff >> (8 * lane)) & 255u) != 0;
    }
    return bad;
}

static uint32_t boundary(uint32_t address) {
    visibility(0);
    (void)rd(address + NBYTES - 4);
    return rd(TIMER);
}

static int timed(unsigned sample, unsigned cpu_only) {
    uint32_t core1 = 0, core2 = 0;
    restore_input(sample);
#ifdef KWS_K7
    wr(TIMER, 1);
#endif
    uint32_t t0 = rd(TIMER);
    int status = pointwise(&tasks[0], cpu_only, &core1);
    uint32_t t1 = boundary(B);
    if (status == CIM_OK) run_dw();
    uint32_t t2 = boundary(A);
    if (status == CIM_OK) status = pointwise(&tasks[1], cpu_only, &core2);
    uint32_t t3 = boundary(B);
#ifdef KWS_K7
    wr(TIMER, 0);
#endif
    unsigned bad = compare_final(sample);
    print("KWS_RESULT");
    field(sample); field(cpu_only); field(t3 - t0);
    field(t1 - t0); field(t2 - t1); field(t3 - t2);
    field(core1); field(core2); field(bad); field((uint32_t)status);
    put('\n');
    return status != CIM_OK || bad;
}

#ifdef KWS_DIAGNOSTIC
static void dump(unsigned sample, unsigned cpu_only, unsigned tensor, uint32_t base) {
    enum { CHUNK = 128 };
    for (uint32_t i = 0; i < NBYTES; i += 4) {
        if (i % CHUNK == 0) {
            print("KWS_TENSOR");
            field(sample); field(cpu_only); field(tensor); field(i);
            put(' ');
        }
        uint32_t word = rd(base + i);
        for (unsigned lane = 0; lane < 4; ++lane)
            hex((uint8_t)(word >> (8 * lane)), 2);
        if ((i + 4) % CHUNK == 0 || i + 4 == NBYTES) put('\n');
    }
}

static int diagnostic(unsigned sample, unsigned cpu_only) {
    uint32_t core;
    restore_input(sample);
    if (pointwise(&tasks[0], cpu_only, &core) != CIM_OK) return 1;
    dump(sample, cpu_only, 24, B);
    run_dw();
    visibility(0);
    dump(sample, cpu_only, 25, A);
    if (pointwise(&tasks[1], cpu_only, &core) != CIM_OK) return 1;
    dump(sample, cpu_only, 26, B);
    return 0;
}
#endif

int main(void) {
    print("CIM_BOOT KWS PW2-DW3-PW4\n");
    int failed = 0;
    for (unsigned sample = 0; sample < CASES && !failed; ++sample) {
        failed = timed(sample, 0);
        if (!failed) failed = timed(sample, 1);
    }
#ifdef KWS_DIAGNOSTIC
    for (unsigned sample = 0; sample < CASES && !failed; ++sample) {
        failed = diagnostic(sample, 0);
        if (!failed) failed = diagnostic(sample, 1);
    }
#endif
    print(failed ? "CIM_FAIL\n" : "CIM_PASS\n");
#ifndef KWS_K7
    wr(SIM_EXIT, 1);
#endif
    return failed;
}
