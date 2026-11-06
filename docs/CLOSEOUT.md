# v0.4.0 release checks

The release includes KWS source
[`a37a911`](https://github.com/zlsjtj/riscv-cim-accelerator/commit/a37a911)
and the original evidence
[`6002694`](https://github.com/zlsjtj/riscv-cim-accelerator/commit/6002694).
The release presentation changes do not rebuild the K7 bitstream or alter
the RTL, firmware, fixture preparation or original evidence files.
[Original board build hashes](evidence/kws_subgraph/k7_build.json)

## Clean reference and open CPU run

Exported tracked files with `git archive 6002694` into a new directory.
Fixture preparation used Windows Python 3.12 and TensorFlow 2.16.1.
The public CPU simulation used WSL Ubuntu 24.04, Python 3.12.3,
Verilator 5.020 and RV32 GCC 13.2.0.

```text
python tools/prepare_kws.py
MAKEFLAGS=-j3 python3 tools/run_ibex.py --out /root/cim-closeout-verified
MAKEFLAGS=-j3 python3 tools/run_ibex.py --kws build/kws_fixture --diagnostic --out /root/cim-closeout-verified
```

- Reference preparation reproduced the two 24,000-byte integer checks.
  The clean Ibex run used the same packed fixture SHA-256 as the archive.
- M1 completed with one START, one DONE and both 64-byte outputs checked.
- KWS reproduced all four timed stage and total cycle counts, hardware
  event counts and twelve diagnostic tensor hashes. The independent
  diagnostic checked 96,000 bytes. The locally linked ELF had a different
  SHA-256. The archived ELF identity still applies to the original run.
  [Archived Ibex result](evidence/kws_subgraph/ibex.json)
- On the reference workstation, the first Ibex build and smoke run took
  about two minutes, and the diagnostic with the model already built
  took about six minutes. [Public dependencies and default paths](REPRODUCE.md)

## Presentation and provenance

- The bar chart derives lengths from `total_cycles / 50,000`. Both
  samples start at zero on the same 0–140 ms scale. Labels are in ms
  and rounded to two decimals. The K7 JSON and stage-cycle sums are
  the source for both home pages. [Board JSON](evidence/kws_subgraph/k7_board.json)
- The architecture distinguishes MMIO control from SRAM data and shows
  two accelerator submissions separated by a CPU depthwise operation.
  The three figures have editable SVG sources and opaque PNG exports.
  [Generator](assets/generate.py) · [Figure source and sizes](assets/figure_spec.json)
- The archive retains the older reference results and K7 evidence.
  [History](STATUS_HISTORY.md)
- The public badge reflects [RTL and Ibex M1 CI](https://github.com/zlsjtj/riscv-cim-accelerator/actions/workflows/rtl.yml).
  The K7 results remain dated board measurements from November 7, 2026.
