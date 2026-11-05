#include "cim.h"

/* Call from the existing BSP after mapping these SRAM regions uncached. */
int cim_example(const cim_device *device, const cim_task *task,
                volatile uint8_t *weight_sram, volatile uint8_t *param_sram,
                const int8_t weights[64][64], const cim_param params[64],
                uint32_t *cycles) {
    uint8_t packed_w[4096], packed_p[768];
    unsigned i;
    int result = cim_validate(task, weights, params);
    if (result != CIM_OK) return result;
    if (!device || !device->read32 || !weight_sram || !param_sram)
        return CIM_EINVAL;
    if (device->read32(device->context, CIM_STATUS) & CIM_BUSY) return CIM_EBUSY;
    /* Input q bytes must already be stored at task->a_base. No bias correction. */
    cim_pack_weights(packed_w, weights);
    cim_pack_params(packed_p, params);
    for (i = 0; i < 4096; ++i) weight_sram[i] = packed_w[i];
    for (i = 0; i < 768; ++i) param_sram[i] = packed_p[i];
    result = cim_submit(device, task);
    if (result != CIM_OK) return result;
    result = cim_wait(device, 10000000u, cycles);
    if (result == CIM_OK) cim_ack(device);
    return result;
}
