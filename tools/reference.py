"""Independent direct INT8 MAC golden; TensorFlow 2.16.1 double rounding.

No nibble decomposition is used here. Official gemmlowp comparison is performed
by tools/check_reference.py before the RTL simulation.
"""
import json
import hashlib
import math
import random
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A, W, P, Y = 0x1000, 0x4000, 0x6000, 0x8000


def trunc_div(n, d):
    return (1 if n >= 0 else -1) * (abs(n) // d)


def multiply(x, multiplier, shift):
    assert -(1 << 31) <= x < (1 << 31)
    assert 0 <= multiplier < (1 << 31) and -31 <= shift <= 0
    product = x * multiplier
    nudge = (1 << 30) if product >= 0 else 1 - (1 << 30)
    high = trunc_div(product + nudge, 1 << 31)
    exponent = -shift
    mask = (1 << exponent) - 1
    remainder = high & mask
    threshold = (mask >> 1) + int(high < 0)
    return (high >> exponent) + int(remainder > threshold)


def quantize(x, multiplier, shift):
    return max(-128, min(127, multiply(x, multiplier, shift) - 128))


def quantize_multiplier(scale):
    if scale == 0:
        return 0, 0
    assert scale > 0 and math.isfinite(scale)
    q, shift = math.frexp(scale)
    fixed = math.floor(q * (1 << 31) + 0.5)
    if fixed == 1 << 31:
        fixed //= 2
        shift += 1
    if shift < -31:
        return 0, 0
    if shift > 0:
        raise ValueError('hardware only supports shift -31..0')
    return fixed, shift


def validate(weights, bias, mult, shift):
    assert len(weights) == len(bias) == len(mult) == len(shift) == 64
    for o in range(64):
        assert len(weights[o]) == 64 and all(-128 <= x <= 127 for x in weights[o])
        lo = bias[o] + sum(255 * min(x, 0) for x in weights[o])
        hi = bias[o] + sum(255 * max(x, 0) for x in weights[o])
        if lo < -(1 << 31) or hi >= 1 << 31:
            raise ValueError(f'channel {o} accumulator may overflow INT32')
        if not 0 <= mult[o] < 1 << 31 or not -31 <= shift[o] <= 0:
            raise ValueError(f'channel {o} unsupported quantization')


def make_case(index, m, model=None, activation=None):
    rng = random.Random(0xC1A000 + index)
    x = [[rng.randrange(-128, 128) for _ in range(64)] for _ in range(m)]
    # Include exact zero input, all-ones nibbles, negative weights and U14 MSB.
    x[0] = [127 if i % 3 else -128 for i in range(64)]
    if activation is not None:
        x = activation[:m]
        assert len(x)==m and all(len(row)==64 and all(-128<=v<=127 for v in row) for row in x)
    if model:
        weights, bias, mult, shift = (model[k] for k in ('weights', 'bias', 'multiplier', 'shift'))
    else:
        weights = [[rng.randrange(-128, 128) for _ in range(64)] for _ in range(64)]
        weights[0] = [127] * 64
        weights[1] = [-128] * 64
        weights[2] = [15] * 64
        bias = [rng.randrange(-6000, 6001) for _ in range(64)]
        mult, shift = zip(*(quantize_multiplier(0.0027 + rng.random() * 0.004) for _ in range(64)))
        mult, shift = list(mult), list(shift)
    validate(weights, bias, mult, shift)
    mem = bytearray(65536)
    for p, row in enumerate(x):
        mem[A+64*p:A+64*p+64] = bytes(v & 255 for v in row)
    for t in range(8):
        for i in range(64):
            for j in range(8):
                mem[W+512*t+8*i+j] = weights[8*t+j][i] & 255
    for o in range(64):
        struct.pack_into('<iii', mem, P+12*o, bias[o], mult[o], shift[o])
    golden = []
    for row in x:
        for o in range(64):
            acc = bias[o] + sum((q+128)*w for q, w in zip(row, weights[o]))
            golden.append(quantize(acc, mult[o], shift[o]) & 255)
    out = ROOT / 'build/vectors'
    out.mkdir(parents=True, exist_ok=True)
    (out / f'mem{index}.hex').write_text('\n'.join(f'{b:02x}' for b in mem)+'\n')
    (out / f'gold{index}.hex').write_text('\n'.join(f'{b:02x}' for b in golden)+'\n')
    source='real weights; exported intermediate activation (see activation_metadata.json)' if activation is not None else 'real weights; synthetic activation' if model else 'synthetic weights and activation'
    return {'index': index, 'M': m, 'source': source, 'outputs': len(golden)}


def generate(dataset="synthetic"):
    model_file = ROOT / 'build/model_layer.json'
    model = json.loads(model_file.read_text()) if dataset in ("model", "real") else None
    activation_file=ROOT/'build/layer_activation.json'
    if dataset == "real" and not activation_file.is_file():
        raise ValueError("Real tensor23 missing. Run tools/run.py --real-activations first")
    activation=json.loads(activation_file.read_text()) if dataset == "real" else None
    activation_metadata=None
    if activation is not None:
        activation_metadata=json.loads((ROOT/'build/activation_metadata.json').read_text())
        raw=bytes(v & 255 for row in activation for v in row)
        if (activation_metadata['tensor']!=23 or activation_metadata['shape']!=[1,25,5,64]
            or len(raw)!=8000 or hashlib.sha256(raw).hexdigest()!=activation_metadata['activation_sha256']
            or activation_metadata['model_sha256']!=hashlib.sha256((ROOT/'build/deps/kws_ref_model.tflite').read_bytes()).hexdigest()
            or activation_metadata['host_layer_check']['status']!='PASS'):
            raise ValueError('Intermediate activation/model/provenance mismatch; re-export before RTL regression')
    cases = [make_case(0, 1), make_case(1, 125), make_case(2, 1), make_case(3, 125)]
    if model:
        # Preserve the established real-weight/synthetic-input cases as controls.
        cases += [make_case(4, 125, model), make_case(5, 1, model)]
        if activation is not None:
            cases += [make_case(6, 125, model, activation),make_case(7, 1, model, activation)]
            for case in cases[-2:]:
                case['activation_metadata']='build/activation_metadata.json'
                case['activation_sha256']=activation_metadata['activation_sha256']
                case['input_rows']='all 125 rows' if case['M']==125 else 'first spatial row (p=0)'
    # Append scheduler boundaries while retaining stable indices of the
    # existing synthetic and model fixtures used in earlier evidence.
    for m in (2, 3, 124):
        cases.append(make_case(len(cases), m))
    (ROOT/'build/vectors/cases.json').write_text(json.dumps(cases, indent=2))
    (ROOT/'build/vectors/m_values.hex').write_text('\n'.join(f'{c["M"]:02x}' for c in cases)+'\n')
    print('REFERENCE generated', cases)
    return cases


if __name__ == '__main__':
    generate()
