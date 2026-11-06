// SPDX-License-Identifier: Apache-2.0
#include "cim.h"

enum {
    SIM_OUT = 0x20000, SIM_EXIT = 0x20008, MTIME_LO = 0x30000, CIM_BASE = 0x40000,
    DATA_BASE = 0x110000, MID = DATA_BASE + 0x6000, FINAL = DATA_BASE + 0x8000,
    GOLD1 = DATA_BASE + 0xa000, GOLD2 = DATA_BASE + 0xc000
};

static uint32_t read_word(uint32_t address) {
    return *(volatile const uint32_t *)(uintptr_t)address;
}

static void write_word(uint32_t address, uint32_t value) {
    *(volatile uint32_t *)(uintptr_t)address = value;
}

static uint32_t cfg_read(void *context, uint32_t offset) {
    (void)context;
    return read_word(CIM_BASE + offset);
}

static void cfg_write(void *context, uint32_t offset, uint32_t value) {
    (void)context;
    write_word(CIM_BASE + offset, value);
}

static void fence(void *context) {
    (void)context;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
}

static void print(const char *text) {
    while (*text) write_word(SIM_OUT, (uint8_t)*text++);
}

static void hex(uint32_t value, unsigned digits) {
    static const char table[] = "0123456789abcdef";
    while (digits) write_word(SIM_OUT, table[(value >> (4 * --digits)) & 15]);
}

static unsigned check_dump(const char *label, uint32_t output, uint32_t golden) {
    unsigned mismatches = 0;
    print(label);
    for (unsigned offset = 0; offset < CIM_M_ROWS * 64u; offset += 4) {
        uint32_t word = read_word(output + offset);
        uint32_t want = read_word(golden + offset);
        for (unsigned lane = 0; lane < 4; ++lane) {
            uint8_t byte = word >> (8 * lane);
            hex(byte, 2);
            mismatches += byte != (uint8_t)(want >> (8 * lane));
        }
    }
    print("\n");
    return mismatches;
}

int main(void) {
    static const cim_device dev = {0, cfg_read, cfg_write, fence, fence};
    static const cim_task first = {CIM_M_ROWS, DATA_BASE + 0x1000, DATA_BASE + 0x3000,
                                   DATA_BASE + 0x5000, MID, 1};
    static const cim_task second = {CIM_M_ROWS, MID, DATA_BASE + 0x4000,
                                    DATA_BASE + 0x5400, FINAL, 1};
    uint32_t bytes = CIM_M_ROWS * 64u;
    print("CIM_BOOT Ibex RV32IM\n");
    for (uint32_t offset = 0; offset < bytes; offset += 4) {
        write_word(MID + offset, ~read_word(GOLD1 + offset));
        write_word(FINAL + offset, ~read_word(GOLD2 + offset));
    }
    fence(0);
    uint32_t start = read_word(MTIME_LO);
    int status = cim_submit_pair_with_options(&dev, &first, &second,
                                               CIM_RETAIN | CIM_PREFETCH | CIM_EARLY_WRITE);
    if (status == CIM_OK) status = cim_wait(&dev, 100000, 0);
    (void)read_word(FINAL + bytes - 4);
    fence(0);
    uint32_t elapsed = read_word(MTIME_LO) - start;
    uint32_t core = cfg_read(0, CIM_CYCLES);

    unsigned bad_mid = check_dump("MID ", MID, GOLD1);
    unsigned bad_final = check_dump("FINAL ", FINAL, GOLD2);
    print("CIM_RESULT "); hex(CIM_M_ROWS, 8);
    print(" "); hex(elapsed, 8);
    print(" "); hex(core, 8);
    print(" "); hex(bad_mid, 8);
    print(" "); hex(bad_final, 8);
    print(" "); hex((uint32_t)status, 8);
    print("\n");
    int failed = status != CIM_OK || bad_mid || bad_final;
    print(failed ? "CIM_FAIL\n" : "CIM_PASS\n");
    write_word(SIM_EXIT, 1);
    return failed;
}
