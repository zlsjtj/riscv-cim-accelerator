"""One-command reference + real RTL regression. No FPGA target is assumed."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from reference import ROOT, generate
from check_reference import check
from variants import DEFAULT_VARIANT, VARIANTS


def command(args, log):
    print('RUN', ' '.join(map(str,args)), flush=True)
    result = subprocess.run(list(map(str,args)), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
    (ROOT/'build'/log).write_text(result.stdout, encoding='utf-8')
    print(result.stdout[-8000:], flush=True)
    if result.returncode:
        raise RuntimeError(f'{log}: exit {result.returncode}; see build/{log}')
    return result.stdout


def simulate(sim, top, plusargs, compile_log, simulation_log, generics=()):
    sources = ['rtl/cim_macro.sv', 'rtl/requant.sv']
    if top == 'tb_accel':
        sources.append('rtl/cim_accel.sv')
    sources.append(f'tb/{top}.sv')
    if sim == 'questa':
        questa = Path(os.environ.get('QUESTA_BIN', 'E:/questasim64_2024.1/win64'))
        if not (ROOT/'build/work').exists():
            command([questa/'vlib.exe', 'build/work'], 'vlib.log')
        command([questa/'vlog.exe', '-sv', '-work', 'build/work', *sources], compile_log)
        return command([questa/'vsim.exe', '-c', '-lib', 'build/work',
                        *(f'-g{arg}' for arg in generics), top, *plusargs,
                        '-do', 'onbreak {quit -code 1}; onerror {quit -code 1}; run -all; quit -code 0'],
                       simulation_log)
    if sim == 'xsim':
        vivado = Path(os.environ.get('VIVADO_BIN', 'E:/Xilinx/Vivado/2023.2/bin'))
        command([vivado/'xvlog.bat', '--sv', *sources], compile_log)
        overrides = [item for arg in generics for item in ('--generic_top', arg)]
        command([vivado/'xelab.bat', top, '--snapshot', top, '--timescale', '1ns/1ps', *overrides],
                f'{top}_elaborate.log')
        testargs = [item for arg in plusargs for item in ('--testplusarg', arg[1:])]
        return command([vivado/'xsim.bat', top, '--runall', *testargs], simulation_log)
    binary = f'build/{top}.vvp'
    command(['iverilog', '-g2012', '-s', top, '-o', binary,
             *(f'-P{top}.{arg}' for arg in generics), *sources], compile_log)
    return command(['vvp', binary, *plusargs], simulation_log)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--simulator',choices=['auto','questa','xsim','iverilog'],default='auto')
    ap.add_argument('--reference-only',action='store_true')
    ap.add_argument('--p1-only',action='store_true',help='blocking M=1/125, separate P1 evidence log')
    ap.add_argument('--memory', choices=['variable','fixed'], default='variable',
                    help='variable waits/backpressure, or fixed-latency reads and always ready')
    ap.add_argument('--variant', choices=VARIANTS, default=DEFAULT_VARIANT)
    latency = ap.add_mutually_exclusive_group()
    latency.add_argument('--read-latency', type=int, choices=(1, 2, 4, 8))
    latency.add_argument('--sweep-latency', action='store_true', help='test fixed latencies 1, 2, 4 and 8')
    ap.add_argument('--trace-memory', action='store_true', help='log the first task per-edge')
    inputs = ap.add_mutually_exclusive_group()
    inputs.add_argument('--dataset', choices=['synthetic','model','real','matrix'], default='synthetic',
                        help='explicit fixture set; real requires a verified tensor23 export')
    inputs.add_argument('--model', dest='dataset', action='store_const', const='model',
                        help='alias for --dataset model (model weights, synthetic inputs)')
    inputs.add_argument('--real-activations', action='store_true',
                        help='export the pinned tensor23 and then run --dataset real')
    ap.add_argument('--tf-python',help='isolated TensorFlow2.16.1 Python (default build/tf_env interpreter)')
    ap.add_argument('--skip-official-check',action='store_true',help='only for diagnosing the simulator; normal regression checks official reference')
    args=ap.parse_args()
    if args.memory != 'fixed' and (args.read_latency or args.sweep_latency):
        ap.error('latency options require --memory fixed')
    (ROOT/'build').mkdir(exist_ok=True)
    dataset = 'real' if args.real_activations else args.dataset
    print(f'Dataset: {dataset}', flush=True)
    use_model = dataset in ('model', 'real')
    if use_model:
        from export_model import export
        export()
    if args.real_activations:
        from prepare_input import prepare
        model_input=prepare()
        tf_python=Path(args.tf_python) if args.tf_python else ROOT/'build/tf_env'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
        if not tf_python.is_file():
            raise RuntimeError('TF environment missing: python -m venv build/tf_env; install tools/requirements-runtime.txt in that environment, or pass --tf-python')
        command([tf_python,'tools/export_activations.py','--model-input-npy',model_input,
                 '--input-metadata',ROOT/'build/inputs/input_metadata.json'],'activation_export.log')
    if args.skip_official_check:
        notice = 'SKIPPED official reference check (--skip-official-check)'
        (ROOT/'build/reference.log').write_text(notice + '\n', encoding='utf-8')
        print(notice, flush=True)
    else:
        check(use_model=use_model)
    cases=generate(dataset)
    if args.reference_only:return
    questa=os.environ.get('QUESTA_BIN','E:/questasim64_2024.1/win64')
    sim=args.simulator
    if sim=='auto':
        sim='questa' if Path(questa,'vsim.exe').exists() else 'iverilog' if shutil.which('iverilog') else 'xsim'
    if sim == 'iverilog':
        command(['iverilog', '-V'], 'iverilog_version.log')
    if 'PASS tb_units' not in simulate(sim, 'tb_units', [], 'unit_compile.log', 'unit_simulation.log'):
        raise RuntimeError('Simulator did not reach unit PASS')
    plusargs = [f'+NCASES={len(cases)}'] + (['+P1_ONLY'] if args.p1_only else [])
    prefix = 'fixed_' if args.memory == 'fixed' else ''
    if args.memory == 'fixed':
        plusargs.append('+FIXED_MEMORY')
        if args.sweep_latency:
            plusargs.append('+SWEEP_LATENCY')
        elif args.read_latency:
            plusargs.append(f'+READ_LATENCY={args.read_latency}')
    if args.trace_memory:
        plusargs.append('+TRACE_MEMORY')
        if sim == 'iverilog':
            plusargs.append('+VCD_TRACE')
    turn, cache, _ = VARIANTS[args.variant]
    output = simulate(sim, 'tb_accel', plusargs, 'compile.log',
                      prefix + ('p1_simulation.log' if args.p1_only else 'simulation.log'),
                      (f'TURNAROUND={turn}', f'INPUT_CACHE={cache}'))
    if 'PASS ALL RTL' not in output:raise RuntimeError('Simulator did not reach complete RTL PASS')
    if args.p1_only:
        shutil.copyfile(ROOT/f'build/{prefix}results.csv',ROOT/f'build/{prefix}p1_results.csv')
    print('PASS RTL units and complete operator;', 'official reference SKIPPED' if args.skip_official_check else 'official reference PASS')


if __name__=='__main__':
    main()
