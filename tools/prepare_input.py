"""Fetch one pinned, published Speech Commands v2 MFCC test sample.

No audio feature extraction or random input generation occurs here. The source
README documents the format; the original WAV/speaker is not identified by it.
Downloaded data stays in build/, with the publisher's description and labels.
"""
import csv
import hashlib
import io
import json
import urllib.request
from pathlib import Path
import numpy as np
from reference import ROOT

COMMIT = 'cf7c2f2634608a7c0ea7458ab7cb3379f2863424'
BASE = f'https://raw.githubusercontent.com/eembc/benchmark-runner-ml/{COMMIT}/'
SAMPLE = 'tst_000000_Stop_7.bin'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def prepare():
    folder = ROOT / 'build/inputs'
    folder.mkdir(parents=True, exist_ok=True)
    files = {'sample': 'datasets/kws01/' + SAMPLE,
             'labels': 'datasets/kws01/y_labels.csv',
             'format': 'datasets/README.md'}
    paths = {}
    for kind, rel in files.items():
        path = folder / Path(rel).name
        if not path.exists():
            path.write_bytes(urllib.request.urlopen(BASE + rel, timeout=30).read())
        paths[kind] = path
    data = paths['sample'].read_bytes()
    if len(data) != 490:
        raise ValueError(f'Published INT8 49x10 sample must be 490B, got {len(data)}')
    label_rows = [row for row in csv.reader(io.StringIO(paths['labels'].read_text()))
                  if row and row[0].strip() == SAMPLE]
    if len(label_rows) != 1 or [s.strip() for s in label_rows[0]] != [SAMPLE, '12', '7']:
        raise ValueError('Published sample label does not match the fixed input selection')
    inp = np.frombuffer(data, dtype=np.int8).reshape(1, 49, 10, 1)
    npy = folder / 'model_input.npy'
    np.save(npy, inp, allow_pickle=False)
    metadata = {
        'schema_version': 1, 'source_kind': 'published_dataset_mfcc',
        'repository': 'https://github.com/eembc/benchmark-runner-ml',
        'commit': COMMIT, 'sample': SAMPLE,
        'source_url': BASE + files['sample'], 'label_url': BASE + files['labels'],
        'format_url': BASE + files['format'],
        'dataset_per_publisher': 'Speech Commands v2', 'label_name': 'Stop',
        'label_id': 7, 'classes': 12, 'input_shape': [1, 49, 10, 1],
        'input_dtype': 'int8', 'input_bytes': len(data),
        'input_sha256': sha256(data), 'npy_file': str(npy.relative_to(ROOT)),
        'transform': 'INT8 bytes in published order reshaped to NHWC; no requantization',
        'limitations': [
            'Uses published quantized MFCC; raw WAV and speaker identity not recovered.',
            'No audio-to-MFCC recomputation or dataset-wide accuracy evaluation.',
            'Dataset quantization calibration was not regenerated; shape/type and input bytes are checked.',
            'Public source downloaded for local validation; no redistribution license inferred.'
        ]}
    (folder / 'input_metadata.json').write_text(json.dumps(metadata, indent=2))
    print('PASS input preparation:', json.dumps(metadata))
    return npy


if __name__ == '__main__':
    prepare()
