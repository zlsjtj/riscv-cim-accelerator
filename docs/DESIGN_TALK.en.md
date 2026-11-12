# Five-minute design walkthrough

[中文讲解](DESIGN_TALK.md) · [Reproduce the project](REPRODUCE.md)

## 0:00–0:45 · Follow the activation

The firmware restores the 8,000-byte input tensor23 to shared SRAM buffer A. The first pointwise convolution (PW, op2) reads A and writes B. The RISC-V CPU runs the 3×3 depthwise convolution (DW, op3) from B to A. The second PW (op4) reads A and writes tensor26 to B. Point out the two hardware START commands in the [architecture diagram](assets/architecture.svg). The scalar C path runs the same operators in the same firmware. [Memory layout (中文)](KWS_SUBGRAPH.md#sram-布局)

## 0:45–1:45 · Reconstruct the full INT8 product

The activation zero point is −128, so each centered activation `q + 128` splits into two unsigned nibbles. The weight splits into an unsigned low nibble and a signed high nibble. The digital proxy consumes four activation bit planes per launch. The controller extends the returned partial sums and combines the four cross-products with weights 1, 16, 16 and 256. A direct integer MAC checks the reconstruction independently. [Macro](../rtl/cim_macro.sv) · [Controller](../rtl/cim_accel.sv) · [Reference](../tools/reference.py)

## 1:45–2:45 · Reserve before launching

The macro returns a result on a fixed schedule. The controller checks `raw_valid | raw_reserved` before starting it. A banked input scratchpad retains input across output tiles, and two live contexts track accumulation, quantization and writes. If SRAM stalls the final word, its context and request stay live. The final commit releases the context. DONE follows the final write and drain. [Controller](../rtl/cim_accel.sv) · [Handshake and timing (中文)](ARCHITECTURE.md)

## 2:45–3:30 · Quantize and hand off through SRAM

After bias and accumulation, the requantizer applies per-channel multiplication and integer double rounding, then adds the output zero point and clamps to the fused ReLU INT8 range. The CPU waits for PW1 completion, reads its output and runs DW. PW2 consumes the actual DW result. The intermediate reference tensors are used by the host to compare the separate diagnostic capture. [Requantizer](../rtl/requant.sv) · [Firmware](../sw/kws_main.c)

## 3:30–5:00 · Explain the measurement

On the same K7 at 50 MHz with one bitstream and ELF, hybrid Stop and Left each take about 18.68 ms. Scalar RV32IM C takes about 127.70 ms, giving 6.83–6.84× speedup. The timer includes CPU execution, submissions, polling and handoffs. Separate diagnostics check 96,000 bytes across both inputs, both paths and three tensors with zero mismatches. CPU DW accounts for about 94.94% of the hybrid window. Open the [recorded UART replay](DEMO.md) for the original board runs, or show the public Ibex smoke test with `python3 tools/run_ibex.py`. [Board data](evidence/kws_subgraph/k7_board.json) · [Measurement scope (中文)](KWS_SUBGRAPH.md#计时和诊断)
