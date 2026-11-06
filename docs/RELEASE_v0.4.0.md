# v0.4.0 · K7-validated KWS subgraph

Runs the fixed INT8 PW(op2) → CPU DW(op3) → PW(op4) subgraph on the open
Ibex simulator and on Kintex-7. Both PW stages submit their own hardware
START. CPU depthwise consumes the actual intermediate activation in SRAM.

- **6.83–6.84× speedup** on K7 at 50 MHz versus scalar RV32IM C in the same
  firmware and bitstream. Stop and Left take about 18.68 ms on the hybrid
  path. [Original board results](https://github.com/zlsjtj/riscv-cim-accelerator/blob/v0.4.0/docs/evidence/kws_subgraph/k7_board.json)
- **96,000 bytes matched** TensorFlow 2.16.1 in separate diagnostics
  across both samples, paths and all three captured tensors. The four
  timed runs each check 8,000 final bytes.
  [Measurement scope and stage cycles](https://github.com/zlsjtj/riscv-cim-accelerator/blob/v0.4.0/docs/KWS_SUBGRAPH.md)

After installing the open dependencies, start with `python3 tools/run_ibex.py`.
[Quick start, full subgraph and board commands](https://github.com/zlsjtj/riscv-cim-accelerator/blob/v0.4.0/docs/REPRODUCE.md)

The release includes the English and Chinese home pages, editable diagrams,
the original K7 measurements and a short design walkthrough. K7 builds use
Vivado and authorized local JYDD sources. The board run was built from
`a37a911` and archived in `6002694`. Earlier releases retain their original
tags and evidence.
[Current status](https://github.com/zlsjtj/riscv-cim-accelerator/blob/v0.4.0/docs/STATUS.md) ·
[Five-minute walkthrough](https://github.com/zlsjtj/riscv-cim-accelerator/blob/v0.4.0/docs/DESIGN_TALK.md)
