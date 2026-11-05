"""Parse constants in the fixed model; input provenance belongs to each case."""
import argparse
import json
import struct
import sys
import urllib.request
from pathlib import Path
from reference import ROOT, quantize_multiplier, validate

COMMIT='4addd0fa08d216e20637637874e084895f289da4'
URL=f'https://raw.githubusercontent.com/mlcommons/tiny/{COMMIT}/benchmark/training/keyword_spotting/trained_models/kws_ref_model.tflite'


def export():
    sys.path.insert(0,str(ROOT/'build/deps_python'))
    try: import tflite
    except ImportError as exc:
        raise RuntimeError('Install model parser: python -m pip install --target build/deps_python tflite==2.18.0 --no-deps (numpy and flatbuffers required)') from exc
    path=ROOT/'build/deps/kws_ref_model.tflite'
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(urllib.request.urlopen(URL,timeout=30).read())
    model=tflite.Model.GetRootAsModel(path.read_bytes(),0)
    graph=model.Subgraphs(0);op=graph.Operators(2)
    assert model.OperatorCodes(op.OpcodeIndex()).BuiltinCode()==tflite.BuiltinOperator.CONV_2D
    ids=[op.Inputs(i) for i in range(op.InputsLength())]
    assert ids==[23,18,6] and op.Outputs(0)==24,ids
    tensors=[graph.Tensors(i) for i in [23,18,6,24]]
    shapes=[[t.Shape(i) for i in range(t.ShapeLength())] for t in tensors]
    assert shapes==[[1,25,5,64],[64,1,1,64],[64],[1,25,5,64]],shapes
    assert [t.Type() for t in tensors]==[tflite.TensorType.INT8,tflite.TensorType.INT8,tflite.TensorType.INT32,tflite.TensorType.INT8]
    table=op.BuiltinOptions();options=tflite.Conv2DOptions();options.Init(table.Bytes,table.Pos)
    assert options.StrideH()==options.StrideW()==options.DilationHFactor()==options.DilationWFactor()==1
    assert options.Padding()==tflite.Padding.SAME and options.FusedActivationFunction()==tflite.ActivationFunctionType.RELU
    aq,wq,bq,yq=[t.Quantization() for t in tensors]
    assert aq.ZeroPoint(0)==yq.ZeroPoint(0)==-128
    assert wq.ScaleLength()==64 and all(wq.ZeroPoint(i)==0 for i in range(wq.ZeroPointLength()))
    assert wq.QuantizedDimension()==0
    input_scale=float(aq.Scale(0));output_scale=float(yq.Scale(0))
    scales=[float(wq.Scale(i)) for i in range(64)]
    # Promote EACH original float32 scale to Python double before calculation.
    effective=[input_scale*s/output_scale for s in scales]
    params=[quantize_multiplier(s) for s in effective]
    raw=model.Buffers(tensors[1].Buffer()).DataAsNumpy().tobytes()
    flat=struct.unpack('<4096b',raw)
    weights=[list(flat[64*o:64*o+64]) for o in range(64)]
    bias=list(struct.unpack('<64i',model.Buffers(tensors[2].Buffer()).DataAsNumpy().tobytes()))
    mult=[x[0] for x in params];shift=[x[1] for x in params]
    validate(weights,bias,mult,shift)
    layer={'source_url':URL,'commit':COMMIT,'operator':2,'tensor_ids':{'input':23,'weights':18,'bias':6,'output':24},'shapes':shapes,'activation':'RELU','activation_source':'Layer constants only; per-case input provenance in build/vectors/cases.json','input_scale':input_scale,'output_scale':output_scale,'weight_scale':scales,'effective_scale':effective,'weights':weights,'bias':bias,'multiplier':mult,'shift':shift,'parser':'tflite==2.18.0 (FlatBuffers schema parser only; not inference runtime)','quantization_reference':'TensorFlow v2.16.1 TFLITE_SINGLE_ROUNDING=0 INT32 overload'}
    (ROOT/'build/model_layer.json').write_text(json.dumps(layer,indent=2))
    summary={k:v for k,v in layer.items() if k not in ['weights','bias','weight_scale','effective_scale','multiplier','shift']}
    summary.update(weight_range=[min(flat),max(flat)],bias_range=[min(bias),max(bias)],effective_scale_range=[min(effective),max(effective)],shifts=sorted(set(shift)))
    (ROOT/'build/model_metadata.json').write_text(json.dumps(summary,indent=2))
    print('PASS fixed-model metadata/constant extraction:',summary)


if __name__=='__main__':export()
