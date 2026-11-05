#include "cim.h"

#define CIM_BASE      UINT32_C(0x80201000)
#define UART_STATUS   UINT32_C(0x80201100)
#define UART_DATA     UINT32_C(0x80201104)
#define COMMITTED     UINT32_C(0x80201108)
#define RESET_CONTROL UINT32_C(0x8020110c)
#define RESET_STATUS  UINT32_C(0x80201110)
#define RESET_WRITES  UINT32_C(0x80201114)
#define SW_TIMER      UINT32_C(0x80201118)
#define A_BASE        UINT32_C(0x80101000)
#define W_BASE        UINT32_C(0x80104000)
#define P_BASE        UINT32_C(0x80106000)
#define Y_BASE        UINT32_C(0x80108000)
#define A_FIXTURE     UINT32_C(0x8010a000)
#define W_FIXTURE     UINT32_C(0x8010c000)
#define P_FIXTURE     UINT32_C(0x8010d000)
#define Y_GOLDEN      UINT32_C(0x8010d400)

void cim_sw_pointwise(unsigned m, const uint8_t *restrict input,
                      const int8_t *restrict weights, const int32_t *restrict params,
                      uint32_t *restrict output);

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

static void visibility(void *context) {
    (void)context;
    // In-order CPU and uncached SRAM, with CPU stores granted before CIM.
    __asm__ volatile ("" ::: "memory");
}

static void copy_words(uint32_t dest, uint32_t source, uint32_t bytes) {
    for (uint32_t offset = 0; offset < bytes; offset += 4)
        write_word(dest + offset, read_word(source + offset));
}

static void print_char(char ch) {
    while (read_word(UART_STATUS) & 1u) {}
    write_word(UART_DATA, (uint8_t)ch);
}

static void print(const char *str) {
    while (*str)
        print_char(*str++);
}

static void print_hex(uint32_t value) {
    for (int shift = 28; shift >= 0; shift -= 4) {
        uint32_t digit = (value >> shift) & 15u;
        print_char((char)(digit < 10 ? '0' + digit : 'a' + digit - 10));
    }
}

static void prepare_task(uint32_t m) {
    uint32_t bytes = m << 6;
    // Every byte differs from golden until the accelerator writes it. Copy
    // the inputs afterwards so recent CPU stores cannot forward old Y data.
    for (uint32_t offset = 0; offset < bytes; offset += 4)
        write_word(Y_BASE + offset, ~read_word(Y_GOLDEN + offset));
    copy_words(A_BASE, A_FIXTURE, bytes);
    copy_words(W_BASE, W_FIXTURE, 4096);
    copy_words(P_BASE, P_FIXTURE, 768);
}

static int submit_task(const cim_device *dev, uint32_t m, uint32_t mode) {
    const cim_task task = {m, A_BASE, W_BASE, P_BASE, Y_BASE, mode};
    prepare_task(m);
    return cim_submit(dev, &task);
}

static uint32_t count_mismatches(uint32_t bytes) {
    uint32_t mismatches = 0;
    for (uint32_t offset = 0; offset < bytes; offset += 4) {
        uint32_t difference = read_word(Y_BASE + offset) ^ read_word(Y_GOLDEN + offset);
        for (unsigned lane = 0; lane < 4; ++lane) {
            mismatches += (difference & 255u) != 0;
            difference >>= 8;
        }
    }
    return mismatches;
}

static int run_software(uint32_t m) {
    prepare_task(m);
    write_word(SW_TIMER, 1);
    visibility(0);
    cim_sw_pointwise(m, (const uint8_t *)(uintptr_t)A_BASE,
                     (const int8_t *)(uintptr_t)W_BASE, (const int32_t *)(uintptr_t)P_BASE,
                     (uint32_t *)(uintptr_t)Y_BASE);
    visibility(0);
    write_word(SW_TIMER, 0);
    uint32_t cycles = read_word(SW_TIMER);
    uint32_t mismatches = count_mismatches(m << 6);
    print("CPU_RESULT ");
    print_hex(m); print_char(' ');
    print_hex(cycles); print_char(' ');
    print_hex(m << 6); print_char(' ');
    print_hex(mismatches); print_char('\n');
    return !cycles || mismatches != 0;
}

static int run_task(const cim_device *dev, uint32_t m, uint32_t mode) {
    uint32_t bytes = m << 6;
    uint32_t cycles = 0;
    int status = submit_task(dev, m, mode);
    if (status == CIM_OK)
        status = cim_wait(dev, 1000000, &cycles);
    if (status != CIM_OK) {
        print("CIM_DRIVER_ERROR ");
        print_hex((uint32_t)status);
        print("\n");
        return 1;
    }
    uint32_t mismatches = count_mismatches(bytes);
    uint32_t writes = read_word(COMMITTED);
    print("CIM_RESULT ");
    print_hex(mode); print_char(' ');
    print_hex(m); print_char(' ');
    print_hex(cycles); print_char(' ');
    print_hex(bytes); print_char(' ');
    print_hex(mismatches); print_char(' ');
    print_hex(writes); print_char('\n');
    cim_ack(dev);
    return mismatches != 0 || writes != bytes / 4;
}

static void interrupt_task(const cim_device *dev, uint32_t mode) {
    if (submit_task(dev, 125, mode) != CIM_OK)
        return;
    for (uint32_t poll = 0; poll < 1000000; ++poll) {
        if (cfg_read(0, CIM_STATUS) != CIM_BUSY)
            return;
        if (read_word(COMMITTED) != 0) {
            write_word(RESET_CONTROL, 1);
            // The next accepted accelerator read resets this CPU. Returning
            // from the loop means the reset did not occur.
            for (uint32_t wait = 0; wait < 1000000; ++wait)
                (void)read_word(RESET_CONTROL);
            return;
        }
    }
}

static int verify_reset(uint32_t mode) {
    uint32_t snapshot = read_word(RESET_STATUS);
    uint32_t before = read_word(RESET_WRITES);
    uint32_t status = cfg_read(0, CIM_STATUS);
    uint32_t cycles = cfg_read(0, CIM_CYCLES);
    uint32_t retained = 0;
    uint32_t invalid = 0;
    for (uint32_t offset = 0; offset < 8000; offset += 4) {
        uint32_t golden = read_word(Y_GOLDEN + offset);
        uint32_t actual = read_word(Y_BASE + offset);
        retained += actual == golden;
        invalid += actual != golden && actual != ~golden;
    }
    // Read the commit counter after the scan to detect a late old write.
    uint32_t after = read_word(COMMITTED);
    print("CIM_RESET ");
    print_hex(mode); print_char(' ');
    print_hex(snapshot & 7); print_char(' ');
    print_hex(snapshot >> 3); print_char(' ');
    print_hex(before); print_char(' ');
    print_hex(status); print_char(' ');
    print_hex(cycles); print_char(' ');
    print_hex(after); print_char(' ');
    print_hex(retained); print_char(' ');
    print_hex(invalid); print_char('\n');
    return snapshot != (CIM_BUSY | 8u) || before == 0 || before >= 2000 ||
           status != 0 || cycles != 0 || after != 0 || retained != before || invalid != 0;
}

int main(void) {
    static const cim_device dev = {0, cfg_read, cfg_write, visibility, visibility};
    uint32_t epoch = read_word(RESET_CONTROL);
    if (epoch == 0) {
        print("CIM_BOOT RV32IM tensor23 scratchpad\n");
        interrupt_task(&dev, 0);
    } else if (epoch <= 2 && !verify_reset(epoch - 1) &&
               !run_task(&dev, 125, epoch - 1) && !run_task(&dev, 1, epoch - 1)) {
        if (epoch == 2) {
            if (!run_software(1) && !run_software(125)) {
                print("CIM_PASS\n");
                return 0;
            }
        } else {
            interrupt_task(&dev, 1);
        }
    }
    print("CIM_FAIL\n");
    return 1;
}
