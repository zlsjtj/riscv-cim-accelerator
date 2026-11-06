"""Build and run a two-layer task on the pinned Ibex Simple System."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from chain_fixture import populate
from reference import ROOT, make_case


IBEX_URL = "https://github.com/lowRISC/ibex.git"
IBEX_REV = "2373e5dadcfc4f56672962fa242f6a051acc9aca"
SIM = ROOT / "sim/ibex"
CORE = "lowrisc:ibex:ibex_simple_system"
SIM_BINARY = Path("lowrisc_ibex_ibex_simple_system_0/sim-verilator/Vibex_simple_system")


def run(args, *, cwd=None, log=None):
    args = [str(arg) for arg in args]
    if log is None:
        subprocess.run(args, cwd=cwd, check=True)
        return
    print(f"{args[0]} -> {log}", flush=True)
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(args, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        print(log.read_text(encoding="utf-8", errors="replace")[-6000:])
        raise SystemExit(f"{args[0]} exited {result.returncode}. See {log}")


def stage_ibex(directory):
    if not (directory / ".git").is_dir():
        run(["git", "init", "-q", directory])
    git = ["git", "-C", directory]
    head = subprocess.run([*git, "rev-parse", "--verify", "HEAD"], capture_output=True, text=True)
    if head.returncode:
        run([*git, "fetch", "--depth=1", IBEX_URL, IBEX_REV])
        run([*git, "-c", "core.autocrlf=false", "checkout", "--detach", IBEX_REV])
    elif head.stdout.strip() != IBEX_REV:
        raise SystemExit(f"{directory} has a different Ibex revision. Choose a fresh --out.")
    patch = SIM / "simple-system.patch"
    apply = [*git, "apply", "--unidiff-zero"]
    reverse = subprocess.run([*apply, "--reverse", "--check", patch], capture_output=True)
    if reverse.returncode:
        run([*apply, patch])
    rtl = directory / "examples/simple_system/rtl/cim"
    rtl.mkdir(exist_ok=True)
    for source in [*sorted((ROOT / "rtl").glob("*.sv")), SIM / "cim_ibex_adapter.sv"]:
        dest = rtl / source.name
        if not dest.exists() or dest.read_bytes() != source.read_bytes():
            shutil.copyfile(source, dest)


def build_firmware(work, m, cc):
    vectors = work / "vectors"
    make_case(0, 125, out=vectors)
    ram = bytearray(65536)
    fixture = populate(ram, 0, vectors)
    (work / "fixture.bin").write_bytes(ram)
    (work / "fixture.S").write_text('.section .fixture,"a",@progbits\n.incbin "fixture.bin"\n')
    run([cc, "-march=rv32im", "-mabi=ilp32", "-Os", "-ffreestanding", "-fno-builtin",
         "-msmall-data-limit=0", "-mno-relax", "-ffunction-sections", "-fdata-sections",
         "-nostdlib", "-Wl,--gc-sections,--no-relax", f"-DCIM_M_ROWS={m}",
         "-I", ROOT / "sw", "-T", SIM / "link.ld", ROOT / "sw/k7_boot.S",
         SIM / "main.c", ROOT / "sw/cim.c", "fixture.S", "-lgcc", "-o", "firmware.elf"],
        cwd=work, log=work / "firmware.log")
    return ram, fixture


def verify(work, m, ram, fixture):
    cpu = (work / "ibex_simple_system.log").read_text(encoding="ascii", errors="replace").splitlines()
    sim = (work / "simulator.log").read_text(encoding="ascii", errors="replace")
    if cpu[:1] != ["CIM_BOOT Ibex RV32IM"] or cpu[-1:] != ["CIM_PASS"]:
        raise SystemExit(f"Missing CPU completion. See {work / 'ibex_simple_system.log'}")
    result = re.fullmatch(r"CIM_RESULT ((?:[0-9a-f]{8} ){5}[0-9a-f]{8})", cpu[-2])
    if len(cpu) != 5 or not result:
        raise SystemExit("Unexpected firmware transcript")
    rows, elapsed, core, mid_bad, final_bad, status = (int(value, 16) for value in result[1].split())
    if rows != m or not 0 < core < elapsed or mid_bad or final_bad or status:
        raise SystemExit("Invalid CPU result")
    hardware = re.findall(r"^CIM_HW (\d+) (\d+) (\d+) (\d+)\s*$", sim, re.M)
    if hardware != [("1", "1", str(2432 + 16*m), str(32*m))]:
        raise SystemExit(f"Unexpected START/DONE/SRAM counts. See {work / 'simulator.log'}")
    checks = {}
    for line, label, name, offset in ((cpu[1], "MID ", "intermediate", 0xa000),
                                       (cpu[2], "FINAL ", "final", 0xc000)):
        if not line.startswith(label):
            raise SystemExit(f"Missing {name} output")
        actual = bytes.fromhex(line[len(label):])
        if actual != ram[offset:offset+64*m]:
            raise SystemExit(f"Host golden mismatch in {name}")
        (work / f"{name}.bin").write_bytes(actual)
        checks[name] = {"bytes": len(actual), "sha256": hashlib.sha256(actual).hexdigest()}
    report = dict(ibex_revision=IBEX_REV, M=m, cpu_cycles=elapsed, accelerator_cycles=core,
                  starts=1, done=1, shared_reads=2432+16*m, shared_writes=32*m,
                  fixture_sha256=fixture["sha256"], outputs=checks)
    (work / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS Ibex M={m}: {64*m} bytes per layer, CPU window {elapsed} cycles, "
          f"CiM {core} cycles\nResults: {work}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m", type=int, choices=(1, 125), default=1)
    parser.add_argument("--out", type=Path, default=ROOT / "build/ibex")
    args = parser.parse_args()
    cc = os.environ.get("RISCV_CC", "riscv64-unknown-elf-gcc")
    for tool in ("git", "fusesoc", "verilator", "g++", "make", cc):
        if not shutil.which(tool):
            parser.error(f"missing {tool}. See docs/IBEX.md for dependencies")
    out = args.out.resolve()
    work = out / f"M{args.m}"
    work.mkdir(parents=True, exist_ok=True)
    for name in ("result.json", "intermediate.bin", "final.bin", "ibex_simple_system.log"):
        (work / name).unlink(missing_ok=True)
    upstream = out / "upstream"
    stage_ibex(upstream)
    ram, fixture = build_firmware(work, args.m, cc)
    sim = out / "sim"
    run(["fusesoc", "--cores-root", upstream, "run", "--target=sim", "--setup", "--build",
         "--build-root", sim, CORE], cwd=upstream, log=out / "build.log")
    # The segmented loader honors the 0x80 boot offset and fixture LMA.
    run([sim / SIM_BINARY, "-c", 5_000_000, "--load-elf=firmware.elf"],
        cwd=work, log=work / "simulator.log")
    verify(work, args.m, ram, fixture)


if __name__ == "__main__":
    main()
