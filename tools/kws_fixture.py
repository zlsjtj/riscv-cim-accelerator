"""Runtime SRAM layout and output verification for the fixed KWS subgraph."""

import hashlib
import json

CASES = ("tst_000000_Stop_7.bin", "tst_000001_Left_2.bin")
TENSOR_BYTES = 8000
CHUNK_BYTES = 128
PARAMETERS = {
    "pw1_weights": (0x3000, 4096), "pw2_weights": (0x4000, 4096),
    "pw1_params": (0x5000, 768), "pw2_params": (0x5400, 768),
    "dw_weights": (0x5800, 576), "dw_params": (0x5c00, 768),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def input_offset(case):
    return 0x8000 + 0x4000 * case


def load_fixture(directory):
    metadata = json.loads((directory / "manifest.json").read_text())
    image = (directory / "fixture.bin").read_bytes()
    if (len(image) != 65536 or digest(image) != metadata["fixture_sha256"] or
            [case["sample"] for case in metadata["cases"]] != list(CASES) or
            any(case["mismatches"] for case in metadata["cases"])):
        raise ValueError("Invalid KWS fixture. Run tools/prepare_kws.py with TensorFlow 2.16.1")
    return image, metadata


def parse_results(output, fixture, diagnostic, out):
    metadata = load_fixture(fixture)[1]
    expected = {(case, mode) for case in range(len(CASES)) for mode in range(2)}
    modes, chunks = {}, {}
    passed = False
    for raw in output.splitlines():
        fields = raw.removeprefix("# ").strip().split()
        if fields[:1] == ["KWS_RESULT"]:
            case, mode, total, pw1, dw, pw2, core1, core2, bad, status = (
                int(value, 16) for value in fields[1:])
            if ((case, mode) not in expected or (case, mode) in modes or
                    total != pw1 + dw + pw2 or min(pw1, dw, pw2) <= 0 or bad or status or
                    (mode == 0 and not (0 < core1 <= pw1 and 0 < core2 <= pw2)) or
                    (mode == 1 and (core1 or core2))):
                raise ValueError(f"Invalid timed KWS result: {raw}")
            modes[case, mode] = dict(case=case, sample=CASES[case],
                                     mode=("hybrid", "cpu_only")[mode], total_cycles=total,
                                     pw1_cycles=pw1, dw_cycles=dw, pw2_cycles=pw2,
                                     pw1_core_cycles=core1, pw2_core_cycles=core2,
                                     compared_bytes=TENSOR_BYTES, mismatches=bad)
        elif fields[:1] == ["KWS_TENSOR"]:
            case, mode, tid, offset = (int(value, 16) for value in fields[1:5])
            key = (case, mode, tid)
            if not diagnostic or (case, mode) not in expected or tid not in (24, 25, 26):
                raise ValueError(f"Unexpected diagnostic tensor {key}")
            tensor = chunks.setdefault(key, bytearray())
            data = bytes.fromhex(fields[5])
            if offset != len(tensor) or offset >= TENSOR_BYTES or len(data) != min(CHUNK_BYTES, TENSOR_BYTES-offset):
                raise ValueError(f"Missing, duplicate or invalid chunk in diagnostic tensor {key} at {offset}")
            tensor.extend(data)
        elif fields == ["CIM_PASS"]:
            passed = True
    want_tensors = {(case, mode, tid) for case, mode in expected for tid in (24, 25, 26)}
    if not passed or modes.keys() != expected or chunks.keys() != (want_tensors if diagnostic else set()):
        raise ValueError("Incomplete KWS firmware run")
    tensors = []
    for (case, mode, tid), actual in chunks.items():
        gold = (fixture / f"case{case}" / f"tensor{tid}.bin").read_bytes()
        if (len(actual) != TENSOR_BYTES or actual != gold or
                digest(gold) != metadata["cases"][case]["tensors"][str(tid)]["sha256"]):
            bad = sum(a != b for a, b in zip(actual, gold)) + abs(len(actual)-len(gold))
            raise ValueError(f"Diagnostic tensor {(case, mode, tid)} disagrees with TensorFlow: {bad} bytes")
        method = ("hybrid", "cpu_only")[mode]
        tensors.append(dict(case=case, mode=method, tensor=tid, compared_bytes=len(actual),
                            mismatches=0, sha256=digest(actual)))
    if diagnostic:
        out.mkdir(parents=True, exist_ok=True)
        for (case, mode, tid), actual in chunks.items():
            method = ("hybrid", "cpu_only")[mode]
            (out / f"case{case}_{method}_tensor{tid}.bin").write_bytes(actual)
    return dict(modes=list(modes.values()), diagnostics=tensors,
                fixture_sha256=metadata["fixture_sha256"])
