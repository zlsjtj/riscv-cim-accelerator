"""Extract the locked KWS operators and compare a causal integer chain with TensorFlow."""

import argparse
import csv
import io
import json
import os
from pathlib import Path
import struct
from urllib.request import urlopen

from export_model import COMMIT as MODEL_COMMIT, URL as MODEL_URL
from kws_fixture import CASES, PARAMETERS, TENSOR_BYTES, digest, input_offset
from reference import ROOT, quantize, quantize_multiplier

INPUT_COMMIT = "cf7c2f2634608a7c0ea7458ab7cb3379f2863424"
INPUT_URL = f"https://raw.githubusercontent.com/eembc/benchmark-runner-ml/{INPUT_COMMIT}/datasets/kws01/"
MODEL_SHA = "aeea436800704fce17b17292e4412630ad856e9d777c044c64ef748a880bd0ae"
SAMPLE_SHA = (
    "ccadc642dec19c4a7f9522207ef8f1b60af7164a86894e03b68b7f5b723503e4",
    "98344c4aea43a4cac9c729d01f7ac534310edb81bfe93920843e7cd52c4c21f1",
)
SHAPE = (1, 25, 5, 64)
LAYERS = (
    ("pw1", 2, (23, 18, 6, 24), (64, 1, 1, 64)),
    ("dw", 3, (24, 8, 7, 25), (1, 3, 3, 64)),
    ("pw2", 4, (25, 19, 9, 26), (64, 1, 1, 64)),
)


def fetch(directory, url, expected_sha):
    path = directory / url.rsplit("/", 1)[1]
    if not path.is_file():
        with urlopen(url, timeout=45) as response:
            data = response.read()
        if digest(data) != expected_sha:
            raise ValueError(f"Unexpected SHA-256 for {url}")
        path.write_bytes(data)
    data = path.read_bytes()
    if digest(data) != expected_sha:
        raise ValueError(f"Unexpected SHA-256 for {path}")
    return data


def extract(model_data, schema, np, image):
    model = schema.Model.GetRootAsModel(model_data, 0)
    graph = model.Subgraphs(0)
    reference, report = [], []
    for name, op_id, ids, weight_shape in LAYERS:
        depthwise = name == "dw"
        op = graph.Operators(op_id)
        want_op = schema.BuiltinOperator.DEPTHWISE_CONV_2D if depthwise else schema.BuiltinOperator.CONV_2D
        opcode = model.OperatorCodes(op.OpcodeIndex())
        assert max(opcode.BuiltinCode(), opcode.DeprecatedBuiltinCode()) == want_op
        assert tuple(op.InputsAsNumpy()) + tuple(op.OutputsAsNumpy()) == ids
        inp, weights, bias, out = (graph.Tensors(tid) for tid in ids)
        assert [tuple(t.ShapeAsNumpy()) for t in (inp, weights, bias, out)] == [SHAPE, weight_shape, (64,), SHAPE]
        assert [t.Type() for t in (inp, weights, bias, out)] == [
            schema.TensorType.INT8, schema.TensorType.INT8, schema.TensorType.INT32, schema.TensorType.INT8]
        opts = schema.DepthwiseConv2DOptions() if depthwise else schema.Conv2DOptions()
        table = op.BuiltinOptions()
        opts.Init(table.Bytes, table.Pos)
        assert opts.StrideH() == opts.StrideW() == opts.DilationHFactor() == opts.DilationWFactor() == 1
        assert opts.Padding() == schema.Padding.SAME and opts.FusedActivationFunction() == schema.ActivationFunctionType.RELU
        assert not depthwise or opts.DepthMultiplier() == 1
        aq, wq, yq = (t.Quantization() for t in (inp, weights, out))
        assert tuple(aq.ZeroPointAsNumpy()) == tuple(yq.ZeroPointAsNumpy()) == (-128,)
        assert wq.ScaleLength() == 64 and wq.QuantizedDimension() == (3 if depthwise else 0)
        assert all(z == 0 for z in wq.ZeroPointAsNumpy())
        raw_w = model.Buffers(weights.Buffer()).DataAsNumpy().tobytes()
        w = np.frombuffer(raw_w, dtype=np.int8).reshape(3, 3, 64) if depthwise else np.frombuffer(raw_w, dtype=np.int8).reshape(64, 64)
        raw_b = model.Buffers(bias.Buffer()).DataAsNumpy().tobytes()
        b = np.frombuffer(raw_b, dtype="<i4").astype(np.int64)
        scales = [float(aq.Scale(0))*float(wq.Scale(c))/float(yq.Scale(0)) for c in range(64)]
        params = [quantize_multiplier(scale) for scale in scales]
        per_channel = w.reshape(-1, 64).T if depthwise else w
        lo = b + 255*np.minimum(per_channel, 0).sum(axis=1)
        hi = b + 255*np.maximum(per_channel, 0).sum(axis=1)
        assert int(lo.min()) >= -(1 << 31) and int(hi.max()) < 1 << 31
        assert all(0 <= mul < 1 << 31 and -31 <= shift <= 0 for mul, shift in params)
        packed = raw_w if depthwise else w.reshape(8, 8, 64).transpose(0, 2, 1).tobytes()
        packed_params = b"".join(struct.pack("<iii", bias, *param) for bias, param in zip(b, params))
        for suffix, data in (("weights", packed), ("params", packed_params)):
            offset, length = PARAMETERS[f"{name}_{suffix}"]
            assert len(data) == length
            image[offset:offset+length] = data
        reference.append((w.astype(np.int64), b, params))
        report.append(dict(layer=name, operator=op_id, tensors=list(ids), weight_shape=weight_shape,
                           weights_sha256=digest(packed), parameters_sha256=digest(packed_params),
                           input_scale=float(aq.Scale(0)), output_scale=float(yq.Scale(0)),
                           input_zero_point=-128, output_zero_point=-128, weight_zero_point=0,
                           accumulator_bounds=[int(lo.min()), int(hi.max())]))
    return reference, report


def check_chain(np, reference, tensors):
    actual = tensors[23].copy()
    stages = []
    for (name, op_id, ids, _), (weights, bias, params) in zip(LAYERS, reference):
        input_hash = digest(actual.tobytes())
        if name == "dw":
            padded = np.pad(actual[0].astype(np.int64) + 128, ((1, 1), (1, 1), (0, 0)))
            acc = np.broadcast_to(bias, (25, 5, 64)).copy()
            for ky in range(3):
                for kx in range(3):
                    acc += padded[ky:ky+25, kx:kx+5, :] * weights[ky, kx]
        else:
            acc = (actual.reshape(125, 64).astype(np.int64) + 128) @ weights.T + bias
        actual = np.array([quantize(int(value), *param)
                           for row in acc.reshape(125, 64)
                           for value, param in zip(row, params)], dtype=np.int8).reshape(SHAPE)
        tid = ids[-1]
        bad = int(np.count_nonzero(actual != tensors[tid]))
        stages.append(dict(operator=op_id, output_tensor=tid, input_sha256=input_hash,
                           output_sha256=digest(actual.tobytes()), compared_bytes=actual.size, mismatches=bad))
        if bad:
            raise ValueError(f"TensorFlow mismatch in op{op_id}: {bad} bytes")
    return stages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/kws_fixture")
    out = parser.parse_args().out
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import numpy as np
    import tensorflow as tf
    from tensorflow.lite.python import schema_py_generated as schema
    if tf.__version__ != "2.16.1":
        raise ValueError(f"TensorFlow 2.16.1 required, got {tf.__version__}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").unlink(missing_ok=True)
    model = fetch(out, MODEL_URL, MODEL_SHA)
    label_sha = "6cb3709762d53fe64eb00eaf4a75796248bb3c1386f1d1f93ccdb07b071e9698"
    labels = list(csv.reader(io.StringIO(fetch(out, INPUT_URL+"y_labels.csv", label_sha).decode())))
    image = bytearray(65536)
    reference, parameters = extract(model, schema, np, image)
    interpreter = tf.lite.Interpreter(model_content=model, num_threads=1,
                                      experimental_preserve_all_tensors=True,
                                      experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF)
    interpreter.allocate_tensors()
    detail, = interpreter.get_input_details()
    assert tuple(detail["shape"]) == (1, 49, 10, 1) and detail["dtype"] == np.int8
    tensor_details = {item["index"]: item for item in interpreter.get_tensor_details()}
    cases = []
    for case, (sample, checksum, label) in enumerate(zip(CASES, SAMPLE_SHA, ("7", "2"))):
        assert [[field.strip() for field in row] for row in labels
                if row and row[0].strip() == sample] == [[sample, "12", label]]
        data = fetch(out, INPUT_URL + sample, checksum)
        interpreter.set_tensor(detail["index"], np.frombuffer(data, dtype=np.int8).reshape(1, 49, 10, 1))
        interpreter.invoke()
        tensors = {tid: interpreter.get_tensor(tid) for tid in (23, 24, 25, 26)}
        folder = out / f"case{case}"
        folder.mkdir(exist_ok=True)
        exports = {}
        for tid, tensor in tensors.items():
            assert tensor.shape == SHAPE and tensor.dtype == np.int8 and tensor_details[tid]["quantization"][1] == -128
            raw = tensor.tobytes()
            (folder / f"tensor{tid}.bin").write_bytes(raw)
            exports[str(tid)] = dict(sha256=digest(raw), bytes=len(raw),
                                     value_range=[int(tensor.min()), int(tensor.max())])
        stages = check_chain(np, reference, tensors)
        start = input_offset(case)
        image[start:start+TENSOR_BYTES] = tensors[23].tobytes()
        start += 0x2000
        image[start:start+TENSOR_BYTES] = tensors[26].tobytes()
        cases.append(dict(sample=sample, input_url=INPUT_URL+sample, input_sha256=checksum,
                          tensors=exports, stages=stages, compared_bytes=3*TENSOR_BYTES, mismatches=0))
        print(f"PASS {sample}: causal PW(op2) / DW(op3) / PW(op4), {3*TENSOR_BYTES} bytes")
    (out / "fixture.bin").write_bytes(image)
    metadata = dict(tensorflow=tf.__version__, resolver="BUILTIN_REF", numpy=np.__version__,
                    model_commit=MODEL_COMMIT, model_url=MODEL_URL, model_sha256=MODEL_SHA,
                    input_commit=INPUT_COMMIT, labels_sha256=label_sha, parameters=parameters,
                    tensor_shape=SHAPE, cases=cases, fixture_sha256=digest(image))
    (out / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
