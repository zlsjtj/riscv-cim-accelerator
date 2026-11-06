#ifndef CIM_H
#define CIM_H

#include <stddef.h>
#include <stdint.h>

enum {
    CIM_CONTROL = 0x00, CIM_STATUS = 0x04, CIM_M = 0x08,
    CIM_A_BASE = 0x0c, CIM_W_BASE = 0x10, CIM_P_BASE = 0x14,
    CIM_Y_BASE = 0x18, CIM_MODE = 0x1c, CIM_CYCLES = 0x20,
    CIM_MEM_WAIT = 0x24, CIM_MACRO_BUSY = 0x28,
    CIM_W2_BASE = 0x2c, CIM_P2_BASE = 0x30, CIM_Y2_BASE = 0x34
};
enum { CIM_START = 1, CIM_ACK_DONE = 2, CIM_CHAIN = 4 };
enum { CIM_BUSY = 1, CIM_DONE = 2, CIM_ERROR = 4 };
enum { CIM_OK = 0, CIM_EINVAL = -1, CIM_EBUSY = -2,
       CIM_EHW = -3, CIM_ETIMEOUT = -4 };

/* The SRAM parameter ABI is exactly three little-endian signed 32-bit words. */
typedef struct { int32_t bias, multiplier, shift; } cim_param;
typedef struct {
    uint32_t m, a_base, w_base, p_base, y_base, mode;
} cim_task;

/*
 * Platform must map these callbacks to uncached MMIO and visibility operations.
 * prepare() writes back caches / makes CPU stores visible before START;
 * acquire() invalidates result caches after DONE. Both may be simple fences on
 * a coherent or uncached system. These hooks are intentionally mandatory.
 */
typedef struct {
    void *context;
    uint32_t (*read32)(void *, uint32_t offset);
    void (*write32)(void *, uint32_t offset, uint32_t value);
    void (*prepare)(void *);
    void (*acquire)(void *);
} cim_device;

int cim_validate(const cim_task *task, const int8_t weights[64][64],
                 const cim_param params[64]);
void cim_pack_weights(uint8_t packed[4096], const int8_t weights[64][64]);
void cim_pack_params(uint8_t packed[768], const cim_param params[64]);
int cim_submit(const cim_device *device, const cim_task *task);
/* Both layers share M and MODE. The first output is the second input. */
int cim_submit_pair(const cim_device *device, const cim_task *first, const cim_task *second);
int cim_wait(const cim_device *device, uint32_t poll_limit, uint32_t *cycles);
void cim_ack(const cim_device *device);

#endif
