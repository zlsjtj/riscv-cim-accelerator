"""Lay out two layers in board SRAM using the independent direct-MAC reference."""

import hashlib
import random

from reference import A, W, P, ROOT, make_case, quantize_multiplier


VECTORS = ROOT / "build/vectors"


def load_vector(kind, index, directory):
    return bytes.fromhex((directory / f"{kind}{index}.hex").read_text())


def populate(ram, first_index, directory=VECTORS):
    first_mem = load_vector("mem", first_index, directory)
    middle = load_vector("gold", first_index, directory)
    assert len(ram) == 65536 and len(middle) == 8000
    activation = first_mem[A:A + 8000]
    intermediate = [[value if value < 128 else value - 256 for value in middle[i:i + 64]]
                    for i in range(0, len(middle), 64)]
    seed = 0xC1A00264
    rng = random.Random(seed)
    weights = [[rng.randrange(-24, 25) for _ in range(64)] for _ in range(64)]
    bias = [rng.randrange(3000, 14001) for _ in range(64)]
    mult, shift = zip(*(quantize_multiplier(0.004 + rng.random() * 0.004) for _ in range(64)))
    layer2 = dict(weights=weights, bias=bias, multiplier=mult, shift=shift)
    second = make_case(11, 125, layer2, intermediate, out=directory)
    second_mem = load_vector("mem", second["index"], directory)
    final = load_vector("gold", second["index"], directory)
    segments = {
        "input": (0x1000, activation),
        "layer1_weights": (0x3000, first_mem[W:W + 4096]),
        "layer2_weights": (0x4000, second_mem[W:W + 4096]),
        "layer1_params": (0x5000, first_mem[P:P + 768]),
        "layer2_params": (0x5400, second_mem[P:P + 768]),
        "intermediate_golden": (0xa000, middle),
        "final_golden": (0xc000, final),
    }
    for offset, data in segments.values():
        ram[offset:offset + len(data)] = data
    return {
        "layer2_seed": seed, "intermediate_address": "0x80106000",
        "final_address": "0x80108000", "intermediate_zero_point": -128,
        "sha256": {name: hashlib.sha256(data).hexdigest() for name, (_, data) in segments.items()},
    }
