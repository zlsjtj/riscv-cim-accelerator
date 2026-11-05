"""Fetch fixed official arithmetic dependencies and validate Python against them."""
import os
import random
import shutil
import subprocess
import urllib.request
from pathlib import Path
from reference import ROOT, multiply, quantize_multiplier


def extract_function(text, start):
    at=text.index(start)
    begin=text.index('{',at)
    depth=1
    end=begin+1
    while depth:
        depth += (text[end]=='{') - (text[end]=='}')
        end += 1
    return text[at:end]

COMMIT = '16e8662c34917be0065110bfcd9cc27d30f52fdf'
FILES = ['fixedpoint/fixedpoint.h', 'internal/detect_platform.h']


def check(use_model=False):
    dep = ROOT/'build/deps'
    for rel in FILES:
        p = dep/rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(urllib.request.urlopen(f'https://raw.githubusercontent.com/google/gemmlowp/{COMMIT}/{rel}', timeout=30).read())
    quant_source=dep/'quantization_util.cc'
    if not quant_source.exists():
        quant_source.write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/tensorflow/tensorflow/v2.16.1/tensorflow/lite/kernels/internal/quantization_util.cc',timeout=30).read())
    source=quant_source.read_text()
    license_header=source[:source.index('#include')]
    common=dep/'common.cc'
    if not common.exists():
        common.write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/tensorflow/tensorflow/v2.16.1/tensorflow/lite/kernels/internal/common.cc',timeout=30).read())
    common_source=common.read_text()
    common_license=common_source[:common_source.index('#include')]
    double_source=common_source.split('// Double-rounding MultiplyByQuantizedMultiplier')[1]
    (dep/'official_quantization.inc').write_text(license_header+extract_function(source,'void QuantizeMultiplier(')+'\n'+common_license+extract_function(double_source,'int32_t MultiplyByQuantizedMultiplier(int32_t'))
    compiler = os.environ.get('CXX') or shutil.which('g++') or 'E:/Xilinx/Vivado/2023.2/tps/mingw/9.3.0/win64.o/nt/bin/g++.exe'
    env = dict(os.environ)
    env['PATH'] = str(Path(compiler).parent) + os.pathsep + env['PATH']
    exe = ROOT/'build/reference_official.exe'
    subprocess.run([compiler, '-std=c++11', '-O2', '-I'+str(dep), str(ROOT/'tools/reference_official.cc'), '-o', str(exe)], check=True, env=env)
    rng = random.Random(0x2161)
    cases = [(x,m,s) for x in [-2147483648,-65537,-3,-2,-1,0,1,2,3,65537,2147483647]
             for m in [0,1,1073741824,2147483647] for s in [0,-1,-7,-8,-31]]
    cases += [(rng.randrange(-2147483648,2147483648),rng.randrange(2147483648),rng.randrange(-31,1)) for _ in range(3000)]
    result = subprocess.run([str(exe)], input=''.join(f'M {x} {m} {s}\n' for x,m,s in cases), text=True, capture_output=True, env=env, check=True)
    expected = list(map(int, result.stdout.split()))
    assert len(expected) == len(cases)
    for case, got in zip(cases, expected):
        assert multiply(*case) == got, (case, multiply(*case), got)
    scales=[0.0,2**-40,2**-31,0.002702844686064139,0.006526506741479271,0.5]
    layer=ROOT/'build/model_layer.json'
    if use_model:
        import json
        scales+=json.loads(layer.read_text())['effective_scale']
    result=subprocess.run([str(exe)],input=''.join(f'Q {s:.17g}\n' for s in scales),text=True,capture_output=True,env=env,check=True)
    params=[tuple(map(int,line.split())) for line in result.stdout.splitlines()]
    assert params==[quantize_multiplier(s) for s in scales]
    text = f'PASS official gemmlowp {COMMIT}: {len(cases)} quantization comparisons; TF2.16.1 int32 double-rounding, shift[-31,0]; {len(scales)} official QuantizeMultiplier scale comparisons\n'
    (ROOT/'build/reference.log').write_text(text)
    print(text.strip())


if __name__ == '__main__':
    check()
