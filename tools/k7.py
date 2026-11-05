"""Build, simulate and run the V2.1 K7 prototype using local JYDD CPU sources."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from reference import ROOT, generate

OUT = ROOT / "build/k7_spad"
CPU = ("RF", "Control", "IMMGEN", "CCTL", "ALU", "ACTL", "CSR")
INCLUDES = ("defines", "myCPU_units", "myCPU_m_ext", "myCPU_bitmanip")
EXPECTED = [(0, 125), (0, 1), (1, 125), (1, 1)]
USR_ACCESS = "43494d34"


def run(command, log):
    command = [str(value) for value in command]
    print("RUN", subprocess.list2cmdline(command), flush=True)
    path = OUT / log
    with path.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=OUT, stdout=stream, stderr=subprocess.STDOUT)
    output = path.read_text(encoding="utf-8", errors="replace")
    print(output[-6000:], flush=True)
    if result.returncode:
        raise RuntimeError(f"{log} exited {result.returncode}")
    return output


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def word_image(path, data):
    path.write_text("".join(f"{int.from_bytes(data[i:i+4], 'little'):08x}\n"
                            for i in range(0, len(data), 4)), encoding="ascii")


def cpu_files(source):
    return [source / "common" / f"{name}.sv" for name in CPU] + [
        source / "route_src/myCPU.sv", source / "route_src/uart.sv"]


def cpu_hashes(source):
    files = cpu_files(source) + [source / "common" / f"{name}.sv" for name in INCLUDES]
    missing = [p.relative_to(source).as_posix() for p in files if not p.is_file()]
    if missing:
        raise ValueError(f"Missing JYDD files under {source}: {', '.join(missing)}")
    return {p.relative_to(source).as_posix(): sha(p) for p in files}


def prepared_hashes():
    return {name: sha(OUT / name) for name in ("firmware.mem", "sram.mem",
                                               "cpu_include/myCPU_m_ext.sv")}


def check_prepared(source):
    metadata = OUT / "build_metadata.json"
    if not metadata.is_file():
        raise ValueError("Run k7.py prepare with the same --out and --cpu-source first")
    record = json.loads(metadata.read_text(encoding="utf-8"))
    if record.get("cpu_sources") != cpu_hashes(source) or record.get("prepared_files") != prepared_hashes():
        raise ValueError("CPU sources or generated files differ from prepare. Run k7.py prepare again")


def stage_m_unit(source):
    original = source / "common/myCPU_m_ext.sv"
    data = original.read_bytes()
    old = b"always_ff @(posedge clk or posedge rst)"
    new = b"always_ff @(posedge clk)"
    if data.count(old) != 1:
        raise ValueError(f"Unexpected M-unit reset structure in {original}")
    patched = OUT / "cpu_include/myCPU_m_ext.sv"
    patched.parent.mkdir(exist_ok=True)
    patched.write_bytes(data.replace(old, new, 1))
    return {"source": str(original), "original_sha256": sha(original),
            "staged_sha256": sha(patched), "change": "M-unit reset is sampled on clk"}


def prepare(source, tools):
    sources = cpu_hashes(source)
    cases = generate()
    case = next((case for case in cases if case["M"] == 125 and "activation_sha256" in case), None)
    if case is None:
        raise ValueError("A verified real tensor23 export is required. Run tools/run.py --real-activations.")
    idx = case["index"]
    memory = bytes.fromhex((ROOT / f"build/vectors/mem{idx}.hex").read_text())
    golden = bytes.fromhex((ROOT / f"build/vectors/gold{idx}.hex").read_text())
    activation = memory[0x1000:0x1000+8000]
    if len(golden) != 8000 or hashlib.sha256(activation).hexdigest() != case["activation_sha256"]:
        raise ValueError("Board input fixture disagrees with verified tensor23")
    m_unit = stage_m_unit(source)
    cc = tools / "riscv-none-elf-gcc.exe"
    copy = tools / "riscv-none-elf-objcopy.exe"
    run([cc, "--version"], "gcc_version.log")
    run([cc, "-march=rv32im", "-mabi=ilp32", "-Os", "-ffreestanding",
         "-fno-builtin", "-msmall-data-limit=0", "-mno-relax",
         "-ffunction-sections", "-fdata-sections", "-nostdlib",
         "-Wl,--gc-sections,--no-relax,-Map=firmware.map",
         "-T", ROOT / "sw/k7_boot.ld", ROOT / "sw/k7_boot.S", ROOT / "sw/k7_main.c",
         ROOT / "sw/cim.c", ROOT / "sw/cim_sw.c", "-lgcc", "-o", "firmware.elf"], "firmware_build.log")
    for section in ("text", "data"):
        run([copy, "-O", "binary", "-j", "." + section, "firmware.elf", section + ".bin"],
            "firmware_" + section + ".log")
    text = (OUT / "text.bin").read_bytes()
    ram = bytearray(65536)
    data = (OUT / "data.bin").read_bytes()
    ram[:len(data)] = data
    ram[0xa000:0xa000+8000] = activation
    ram[0xc000:0xd000] = memory[0x4000:0x5000]
    ram[0xd000:0xd300] = memory[0x6000:0x6300]
    ram[0xd400:0xd400+8000] = golden
    word_image(OUT / "sram.mem", ram)
    word_image(OUT / "firmware.mem", text.ljust(16384, b"\x00"))
    metadata = {
        "cpu_source_root": str(source), "cpu_sources": sources,
        "prepared_files": prepared_hashes(),
        "firmware_elf_sha256": sha(OUT / "firmware.elf"), "text_bytes": len(text),
        "fixture_case": idx, "activation_sha256": case["activation_sha256"],
        "golden_sha256": hashlib.sha256(golden).hexdigest(),
        "m_unit_reset_patch": m_unit,
        "fpga_part": "xc7k325tffg900-2", "ref_clock_hz": 200000000, "core_clock_hz": 50000000,
    }
    (OUT / "build_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def parse_results(output):
    rows = []
    for line in output.splitlines():
        match = re.fullmatch(r"(?:# )?CIM_RESULT ((?:[0-9a-f]{8} ){5}[0-9a-f]{8})", line.strip())
        if match:
            mode, m, cycles, count, bad, writes = (int(field, 16) for field in match[1].split())
            if not cycles or count != 64*m or bad != 0 or writes != count//4:
                raise ValueError(f"Invalid result: {line}")
            rows.append(dict(mode=mode, M=m, cycles=cycles, outputs=count,
                             mismatches=bad, committed_words=writes))
    if "CIM_PASS" not in output.split() or [(row["mode"], row["M"]) for row in rows] != EXPECTED:
        raise RuntimeError("Incomplete RV32I result sequence")
    return rows


def parse_resets(output):
    rows = []
    for line in output.splitlines():
        match = re.fullmatch(r"(?:# )?CIM_RESET ((?:[0-9a-f]{8} ){8}[0-9a-f]{8})", line.strip())
        if match:
            mode, pre, pending, before, post, cycles, after, retained, invalid = (
                int(field, 16) for field in match[1].split()
            )
            if (pre != 1 or pending != 1 or not 0 < before < 2000 or
                    (post, cycles, after, invalid) != (0, 0, 0, 0) or retained != before):
                raise ValueError(f"Invalid reset record: {line}")
            rows.append(dict(mode=mode, status_before=pre, read_response_at_reset=pending,
                             committed_before=before, status_after=post, cycles_after=cycles,
                             committed_after=after, retained_words=retained, invalid_words=invalid))
    if [row["mode"] for row in rows] != [0, 1]:
        raise RuntimeError("Expected an in-flight warm reset in each mode")
    return rows


def parse_cpu_results(output):
    rows = []
    for line in output.splitlines():
        match = re.fullmatch(r"(?:# )?CPU_RESULT ((?:[0-9a-f]{8} ){3}[0-9a-f]{8})", line.strip())
        if match:
            m, cycles, count, bad = (int(field, 16) for field in match[1].split())
            if not cycles or count != 64*m or bad:
                raise ValueError(f"Invalid software result: {line}")
            rows.append(dict(M=m, cycles=cycles, outputs=count, mismatches=bad))
    if [row["M"] for row in rows] != [1, 125]:
        raise RuntimeError("Incomplete RV32IM software baseline")
    return rows


def simulate(source, questa, trace_blocks):
    if not (OUT / "work").exists():
        run([questa / "vlib.exe", "work"], "vlib.log")
    sources = cpu_files(source) + sorted((ROOT / "rtl").glob("*.sv")) + [
        ROOT / "fpga/cim_rv_system.sv", ROOT / "tb/tb_rv_system.sv"]
    run([questa / "vlog.exe", "-sv", "+define+CIM_SW_TIMER", f"+incdir+{OUT / 'cpu_include'}+{source / 'common'}",
         *sources], "soc_compile.log")
    # Existing RF and predictor arrays have power-up initializers as well as
    # always_ff writes. Keep the source intact and allow that Questa diagnostic.
    trace_args = ["+TRACE_BLOCKS"] if trace_blocks else []
    output = run([questa / "vsim.exe", "-c", "-voptargs=-suppress 7061", "tb_rv_system", *trace_args, "-do",
                  "onbreak {quit -code 1}; onerror {quit -code 1}; run -all; quit -code 0"],
                 "soc_simulation.log")
    (OUT / "soc_results.json").write_text(json.dumps(parse_results(output), indent=2), encoding="utf-8")
    (OUT / "soc_reset_results.json").write_text(json.dumps(parse_resets(output), indent=2), encoding="utf-8")
    (OUT / "soc_cpu_results.json").write_text(json.dumps(parse_cpu_results(output), indent=2), encoding="utf-8")


def program(vivado, target, port, archive):
    import serial

    bit = archive if archive else OUT / "cim_k7.bit"
    if not bit.is_file() or not target or not port:
        raise ValueError("Program requires a routed bitstream, explicit JTAG serial and COM port")
    log = (bit.parent / "impl_vivado.log").read_text(encoding="utf-8", errors="replace")
    if "K7_BITSTREAM_READY" not in log.splitlines():
        raise ValueError("Last implementation did not pass the bitstream gate")
    metadata = bit.parent / "bitstream_metadata.json"
    if archive and not metadata.is_file():
        metadata = bit.parent / "board_results.json"
    record = json.loads(metadata.read_text(encoding="utf-8"))
    if (record.get("bit_sha256"), record.get("usr_access")) != (sha(bit), USR_ACCESS):
        raise ValueError("Bitstream SHA-256 or USR_ACCESS disagrees with the recorded scratchpad build")
    if not archive and record.get("prepared_files") != prepared_hashes():
        raise ValueError("Prepared images changed since implementation. Run impl again")
    transcript = bytearray()
    with serial.Serial(port, 115200, timeout=0.25) as uart:
        uart.reset_input_buffer()
        run([vivado, "-mode", "batch", "-nojournal", "-log", "program_vivado.log",
             "-source", ROOT / "fpga/program_k7.tcl", "-tclargs", target, bit, USR_ACCESS], "program.log")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            transcript += uart.read(512)
            if b"CIM_PASS\n" in transcript or b"CIM_FAIL\n" in transcript:
                break
    (OUT / "board_uart.log").write_bytes(transcript)
    output = transcript.decode("ascii", errors="replace")
    print(output)
    rows = parse_results(output)
    resets = parse_resets(output)
    result = {"jtag_serial": target, "uart_port": port, "uart_baud": 115200,
              "bit_sha256": sha(bit), "usr_access": USR_ACCESS, "resets": resets, "tasks": rows,
              "software": parse_cpu_results(output)}
    (OUT / "board_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


def main():
    global OUT
    sys.stdout.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("prepare", "sim", "impl", "program"))
    parser.add_argument("--cpu-source", type=Path, help="JYDD source directory with common/ and route_src/")
    parser.add_argument("--gcc-bin", type=Path, help="xPack RV32 GCC bin directory, or put GCC on PATH")
    parser.add_argument("--out", type=Path, default=OUT, help="Build and capture directory (default build/k7_spad)")
    parser.add_argument("--bitstream", type=Path, help="For program, a scratchpad bit beside impl_vivado.log")
    parser.add_argument("--trace-blocks", action="store_true", help="For sim, write task-relative block_trace.csv")
    parser.add_argument("--jtag")
    parser.add_argument("--port")
    args = parser.parse_args()
    if args.bitstream and args.step != "program":
        parser.error("--bitstream requires program")
    if args.trace_blocks and args.step != "sim":
        parser.error("--trace-blocks requires sim")
    if args.step != "program" and args.cpu_source is None:
        parser.error(f"{args.step} requires --cpu-source pointing to authorized local JYDD sources")
    if args.step == "prepare" and args.gcc_bin is None:
        gcc = shutil.which("riscv-none-elf-gcc.exe")
        if not gcc:
            parser.error("prepare requires --gcc-bin or riscv-none-elf-gcc.exe on PATH")
        args.gcc_bin = Path(gcc).parent
    OUT = args.out.resolve()
    source = args.cpu_source.resolve() if args.cpu_source else None
    vivado = Path(os.environ.get("VIVADO_BIN", "E:/Xilinx/Vivado/2023.2/bin")) / "vivado.bat"
    questa = Path(os.environ.get("QUESTA_BIN", "E:/questasim64_2024.1/win64"))
    OUT.mkdir(parents=True, exist_ok=True)
    if args.step in ("sim", "impl"):
        check_prepared(source)
    if args.step == "prepare":
        prepare(source, args.gcc_bin.resolve())
    elif args.step == "sim":
        simulate(source, questa, args.trace_blocks)
    elif args.step == "impl":
        output = run([vivado, "-mode", "batch", "-nojournal", "-log", "impl_vivado.log",
                      "-source", ROOT / "fpga/build_k7.tcl", "-tclargs", source],
                     "implementation.log")
        if "K7_BITSTREAM_READY" not in output.splitlines():
            raise RuntimeError("Implementation did not pass the bitstream gate")
        record = {"bit_sha256": sha(OUT / "cim_k7.bit"), "usr_access": USR_ACCESS,
                  "prepared_files": prepared_hashes()}
        (OUT / "bitstream_metadata.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    else:
        program(vivado, args.jtag, args.port, args.bitstream.resolve() if args.bitstream else None)


if __name__ == "__main__":
    main()
