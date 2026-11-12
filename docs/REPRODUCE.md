# Reproduce the project

Use the [v0.4.0 stable checkout](https://github.com/zlsjtj/riscv-cim-accelerator/tree/v0.4.0).

## Quick start with the open CPU

On Ubuntu 24.04 or WSL with Ubuntu 24.04, install the public toolchain and run the smoke test from the repository root.

~~~bash
sudo apt-get update
sudo apt-get install -y git verilator gcc-riscv64-unknown-elf g++ make libelf-dev python3-venv
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r tools/requirements-ibex.txt
python3 tools/run_ibex.py
~~~

The first run fetches pinned Ibex and builds the Verilator model. Expect
`PASS Ibex M=1` and `build/ibex/M1/{intermediate.bin,final.bin,result.json}`.
The smoke test runs a synthetic two-layer workload. The reference tools were
Python 3.12, Verilator 5.020 and RISC-V GCC 13.2.0. FuseSoC and Edalize
are pinned in the requirements file. [System details (中文)](IBEX.md)

## Real KWS subgraph in Ibex

Use Python 3.12 and TensorFlow 2.16.1. The model, published Stop/Left MFCC
samples, derived weights and tensors are prepared locally.

~~~bash
python3 -m venv .venv-tf
.venv-tf/bin/python -m pip install -r tools/requirements-runtime.txt
.venv-tf/bin/python tools/prepare_kws.py
~~~

The two reference checks each report 24,000 compared bytes. The fixture,
source manifest and golden tensors go to `build/kws_fixture/`.
Activate the Ibex environment and run the timed workload or the workload with diagnostic capture.

~~~bash
source .venv/bin/activate
python3 tools/run_ibex.py --kws build/kws_fixture
python3 tools/run_ibex.py --kws build/kws_fixture --diagnostic
~~~

Either command runs hybrid and scalar CPU paths for both samples in one
ELF. The first produces timing and final-output checks in
`build/ibex/kws/`. The second appends a separate untimed diagnostic
run and writes the twelve checked tensors and `result.json` under
`build/ibex/kws_diagnostic/`. A clean build and diagnostic run take
several minutes on the reference workstation. CPU speed and Verilator
build parallelism affect wall time. [Tensor layout and reference scope (中文)](KWS_SUBGRAPH.md)

## K7 board replay

Use the generated fixture, a Kintex-7 board with JTAG and a UART connection,
Vivado 2023.2, xPack RV32IM GCC and authorized local JYDD CPU/UART sources.
Questa is used for the board SoC simulation step. Commands for
`prepare`, `sim`, `impl` and `program` share one build directory.
[K7 dependencies (中文)](BOARD_K7.md) · [Exact subgraph commands (中文)](KWS_SUBGRAPH.md#复现)

[Archived UART replay](DEMO.md) · [English design walkthrough](DESIGN_TALK.en.md)
