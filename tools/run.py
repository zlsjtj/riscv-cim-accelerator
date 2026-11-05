"""One-command reference + real RTL regression. No FPGA target is assumed."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from reference import ROOT, generate
from check_reference import check


def command(args, log):
    print('RUN', ' '.join(map(str,args)), flush=True)
    result = subprocess.run(list(map(str,args)), cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
    (ROOT/'build'/log).write_text(result.stdout, encoding='utf-8')
    print(result.stdout[-8000:], flush=True)
    if result.returncode:
        raise RuntimeError(f'{log}: exit {result.returncode}; see build/{log}')
    return result.stdout


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--simulator',choices=['auto','questa','xsim','iverilog'],default='auto')
    ap.add_argument('--reference-only',action='store_true')
    ap.add_argument('--p1-only',action='store_true',help='blocking M=1/125, separate P1 evidence log')
    ap.add_argument('--model',action='store_true',help='download/parse fixed weights; include verified exported activations if present')
    ap.add_argument('--real-activations',action='store_true',help='prepare pinned published MFCC input and export tensor23 using TF2.16.1, then full RTL regression')
    ap.add_argument('--tf-python',help='isolated TensorFlow2.16.1 Python (default build/tf_env interpreter)')
    ap.add_argument('--skip-official-check',action='store_true',help='only for diagnosing the simulator; normal regression checks official reference')
    args=ap.parse_args()
    (ROOT/'build').mkdir(exist_ok=True)
    if args.model or args.real_activations:
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
    if not args.skip_official_check: check()
    cases=generate()
    if args.reference_only:return
    sources=['rtl/cim_macro.sv','rtl/requant.sv','rtl/cim_accel.sv','tb/tb_accel.sv']
    questa=os.environ.get('QUESTA_BIN','E:/questasim64_2024.1/win64')
    vivado=os.environ.get('VIVADO_BIN','E:/Xilinx/Vivado/2023.2/bin')
    sim=args.simulator
    if sim=='auto':
        sim='questa' if Path(questa,'vsim.exe').exists() else 'iverilog' if shutil.which('iverilog') else 'xsim'
    if sim=='questa':
        if not Path(ROOT/'build/work').exists():command([Path(questa)/'vlib.exe','build/work'],'vlib.log')
        command([Path(questa)/'vlog.exe','-sv','-work','build/work']+sources,'compile.log')
        output=command([Path(questa)/'vsim.exe','-c','-lib','build/work','tb_accel',f'+NCASES={len(cases)}']+(['+P1_ONLY'] if args.p1_only else [])+['-do','onbreak {quit -code 1}; onerror {quit -code 1}; run -all; quit -code 0'],'p1_simulation.log' if args.p1_only else 'simulation.log')
    elif sim=='xsim':
        command([Path(vivado)/'xvlog.bat','--sv']+sources,'compile.log')
        command([Path(vivado)/'xelab.bat','tb_accel','--snapshot','cim_tb','--timescale','1ns/1ps'],'elaborate.log')
        output=command([Path(vivado)/'xsim.bat','cim_tb','--runall','--testplusarg',f'NCASES={len(cases)}']+(['--testplusarg','P1_ONLY'] if args.p1_only else []),'p1_simulation.log' if args.p1_only else 'simulation.log')
    else:
        command(['iverilog','-g2012','-s','tb_accel','-o','build/sim.vvp']+sources,'compile.log')
        output=command(['vvp','build/sim.vvp',f'+NCASES={len(cases)}']+(['+P1_ONLY'] if args.p1_only else []),'p1_simulation.log' if args.p1_only else 'simulation.log')
    if 'PASS ALL RTL' not in output:raise RuntimeError('Simulator did not reach complete RTL PASS')
    if args.p1_only:
        shutil.copyfile(ROOT/'build/results.csv',ROOT/'build/p1_results.csv')
    print('PASS complete reference + RTL flow;', 'build/p1_results.csv and build/p1_simulation.log' if args.p1_only else 'build/results.csv and build/simulation.log')


if __name__=='__main__':
    main()
