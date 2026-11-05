"""Portable syntax check; target synthesis requires an explicit confirmed part."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def vivado_bin():
    value = os.environ.get("VIVADO_BIN")
    if value:
        return Path(value)
    executable = shutil.which("vivado") or shutil.which("vivado.bat")
    if executable:
        return Path(executable).parent
    candidates = sorted(Path("E:/Xilinx/Vivado").glob("*/bin"), reverse=True)
    return candidates[0] if candidates else None


def run(command, cwd, logfile):
    try:
        with logfile.open("w", encoding="utf-8") as stream:
            result = subprocess.run(command, cwd=cwd, stdout=stream,
                                    stderr=subprocess.STDOUT)
    except OSError as error:
        message = "NOT_RUN: failed to launch tool: " + str(error)
        logfile.write_text(message, encoding="utf-8")
        raise SystemExit(message)
    print(logfile.read_text(encoding="utf-8", errors="replace")[-16000:], end="")
    if result.returncode:
        raise SystemExit(result.returncode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", help="Confirmed exact FPGA part; never inferred")
    parser.add_argument("--period", type=float, help="Confirmed clock period in ns")
    parser.add_argument("--driver", action="store_true", help="Compile/run host C driver checks")
    parser.add_argument("--generic", action="store_true", help="Yosys technology-independent synthesis; no part")
    args = parser.parse_args()
    out = ROOT / "build" / "checks"
    out.mkdir(parents=True, exist_ok=True)
    binary = vivado_bin()
    if args.generic:
        deps = ROOT / "build/python_deps"
        if not (deps / "yowasp_yosys").is_dir():
            raise SystemExit("NOT_RUN: install python -m pip install --target build/python_deps yowasp-yosys")
        yosys_script = ("read_verilog -sv rtl/cim_macro.sv rtl/requant.sv rtl/cim_accel.sv; "
                        "hierarchy -check -top cim_accel; synth -top cim_accel -noabc; "
                        "check -assert; tee -o build/checks/generic_stat.json stat -json; "
                        "write_json build/checks/generic_netlist.json")
        code = ("import sys; sys.path.insert(0, 'build/python_deps'); "
                "import yowasp_yosys; sys.exit(yowasp_yosys.run_yosys(sys.argv[1:]))")
        run([sys.executable, "-c", code, "-p", yosys_script], ROOT, out / "generic_synth.log")
        print("PASS generic synthesis/check only; counts are generic gates, not FPGA LUTs or physical timing.")
        return
    if args.driver:
        compiler = shutil.which("gcc")
        if not compiler and binary:
            candidate = binary.parent / "tps/mingw/9.3.0/win64.o/nt/bin/gcc.exe"
            if candidate.is_file():
                compiler = str(candidate)
        if not compiler:
            raise SystemExit("NOT_RUN host C checks: GCC not found")
        os.environ["PATH"] = str(Path(compiler).parent) + os.pathsep + os.environ["PATH"]
        run([compiler, "--version"], ROOT, out / "gcc_version.log")
        run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-c", str(ROOT / "sw/example.c"), "-o", str(out / "example.o")],
            ROOT, out / "driver_compile.log")
        executable = out / "test_driver.exe"
        run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             str(ROOT / "sw/cim.c"), str(ROOT / "sw/test_driver.c"), "-o", str(executable)],
            ROOT, out / "driver_test_compile.log")
        run([str(executable)], ROOT, out / "driver_test.log")
        return
    if not binary:
        raise SystemExit("NOT_RUN: Vivado/xvlog not found; set VIVADO_BIN")
    if args.part or args.period:
        if not args.part or args.period is None or args.period <= 0:
            parser.error("target synthesis requires both --part and a positive --period")
        run([str(binary / "vivado.bat"), "-mode", "batch", "-nojournal", "-log",
             str(out / "vivado.log"), "-source", str(ROOT / "fpga/synth.tcl"),
             "-tclargs", args.part, str(args.period)], ROOT, out / "synth_console.log")
    else:
        sources = sorted((ROOT / "rtl").glob("*.sv"))
        if not sources:
            raise SystemExit("NOT_RUN syntax: no RTL files found")
        run([str(binary / "xvlog.bat"), "--sv", *map(str, sources)],
            out, out / "syntax.log")
        print("PASS Vivado HDL analysis only. Target synthesis/P&R NOT_RUN: part and clock unknown.")


if __name__ == "__main__":
    main()
