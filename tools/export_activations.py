"""Optional real INTERMEDIATE export, requiring externally supplied model input.

This does not claim the model input comes from a real speech recording/dataset.
No TensorFlow installation is performed automatically. Tested RTL golden remains
the direct MAC + locked double-round reference, never Interpreter tensor24.
"""
import argparse
import hashlib
import json
import platform
from pathlib import Path
from reference import ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model-input-npy',required=True,help='actual whole-model input, exact INT8 model input shape')
    parser.add_argument('--input-origin',help='dataset/sample identity, or explicitly synthetic')
    parser.add_argument('--input-metadata',help='machine-readable source record with input_sha256')
    args=parser.parse_args()
    try:
        import tensorflow as tf
        import numpy as np
    except ImportError as exc:
        raise RuntimeError('NOT_RUN: optional TensorFlow v2.16.1 runtime is not installed') from exc
    if tf.__version__!='2.16.1':
        raise RuntimeError(f'NOT_RUN: locked TensorFlow 2.16.1 required, found {tf.__version__}')
    model=ROOT/'build/deps/kws_ref_model.tflite'
    if not model.exists():
        raise RuntimeError('Run python tools/export_model.py first')
    interpreter=tf.lite.Interpreter(model_path=str(model),experimental_preserve_all_tensors=True,
        experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF)
    interpreter.allocate_tensors()
    input_details=interpreter.get_input_details()
    if len(input_details)!=1:raise RuntimeError('expected one whole-model input')
    details=input_details[0]
    inp=np.load(args.model_input_npy,allow_pickle=False)
    if inp.dtype!=details['dtype'] or list(inp.shape)!=list(details['shape']):
        raise ValueError(f'input must be dtype={details["dtype"]} shape={details["shape"]}, got {inp.dtype} {inp.shape}')
    source = json.loads(Path(args.input_metadata).read_text()) if args.input_metadata else None
    digest = lambda data: hashlib.sha256(data).hexdigest()
    if source and (source['input_sha256'] != digest(inp.tobytes()) or source['input_shape'] != list(inp.shape)):
        raise ValueError('Input source record does not describe the loaded model input bytes')
    if not source and not args.input_origin:
        raise ValueError('Provide --input-metadata or --input-origin; origin may not be omitted')
    interpreter.set_tensor(details['index'],inp);interpreter.invoke()
    activation=interpreter.get_tensor(23)
    assert activation.dtype==np.int8 and list(activation.shape)==[1,25,5,64]
    output=interpreter.get_tensor(24)
    assert output.dtype==np.int8 and list(output.shape)==[1,25,5,64]
    # Verify the host reference before using it as RTL golden. The interpreter
    # output is a cross-check only; RTL golden remains independently computed.
    from reference import quantize, validate
    layer=json.loads((ROOT/'build/model_layer.json').read_text())
    validate(layer['weights'],layer['bias'],layer['multiplier'],layer['shift'])
    flat=activation.reshape(125,64).tolist()
    direct=[]
    for row in flat:
        for o in range(64):
            acc=layer['bias'][o]+sum((q+128)*w for q,w in zip(row,layer['weights'][o]))
            direct.append(quantize(acc,layer['multiplier'][o],layer['shift'][o]))
    ref=np.array(direct,dtype=np.int8).reshape(output.shape)
    mismatch=np.flatnonzero(ref.reshape(-1)!=output.reshape(-1))
    if len(mismatch):
        at=int(mismatch[0]);raise ValueError(f'Host layer mismatch p={at//64} o={at%64}: direct={direct[at]}, interpreter={int(output.reshape(-1)[at])}; count={len(mismatch)}')
    np.save(ROOT/'build/layer_activation.npy',activation,allow_pickle=False)
    np.save(ROOT/'build/layer_interpreter_output.npy',output,allow_pickle=False)
    (ROOT/'build/layer_activation.json').write_text(json.dumps(activation.reshape(125,64).tolist()))
    layer_detail={d['index']:d for d in interpreter.get_tensor_details()}
    metadata={'schema_version':1,'runtime':'TensorFlow 2.16.1 BUILTIN_REF preserve_all_tensors',
        'tensorflow_version':tf.__version__,'numpy_version':np.__version__,'python_version':platform.python_version(),
        'model_commit':'4addd0fa08d216e20637637874e084895f289da4','model_sha256':digest(model.read_bytes()),
        'tensor':23,'tensor_name':layer_detail[23]['name'],'shape':[1,25,5,64],'dtype':'int8',
        'layer_operator':2,'output_tensor':24,'flatten':'NHWC [1,25,5,64] -> [125,64], spatial row-major',
        'model_input_tensor':int(details['index']),'model_input_shape':list(map(int,details['shape'])),
        'model_input_quantization':list(details['quantization']),
        'model_input_file':str(Path(args.model_input_npy).resolve()),
        'model_input_origin':source if source else args.input_origin,'model_input_sha256':digest(inp.tobytes()),
        'activation_sha256':digest(activation.tobytes()),'activation_range':[int(activation.min()),int(activation.max())],
        'activation_unique_values':int(np.unique(activation).size),'activation_bytes':int(activation.size),
        'interpreter_output_sha256':digest(output.tobytes()),
        'host_layer_check':{'status':'PASS','compared_int8':8000,'mismatches':0},
        'golden':'independent direct integer MAC and fixed double-rounding; not interpreter output',
        'evidence_scope':'Actual host inference intermediate from one documented model input; no FPGA or dataset-wide KWS accuracy claim'}
    (ROOT/'build/activation_metadata.json').write_text(json.dumps(metadata,indent=2))
    print('PASS intermediate export:',json.dumps(metadata))


if __name__=='__main__':main()
