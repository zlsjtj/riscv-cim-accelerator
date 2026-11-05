# 目标层真实中间激活的来源与复现

已实际从来源明确的整模型输入运行TensorFlow2.16.1，导出tensor23，再完成
独立整数参考与RTL比较。这里的“真实中间激活”指主机执行固定模型所得的
中间张量；硬件只运行所选点卷积层。

## 来源链

1. 模型：MLCommons Tiny提交 `4addd0fa08d216e20637637874e084895f289da4`，
   [kws_ref_model.tflite](https://github.com/mlcommons/tiny/blob/4addd0fa08d216e20637637874e084895f289da4/benchmark/training/keyword_spotting/trained_models/kws_ref_model.tflite)。
2. 整模型输入：EEMBC benchmark-runner-ml提交
   `cf7c2f2634608a7c0ea7458ab7cb3379f2863424` 的
   [tst_000000_Stop_7.bin](https://github.com/eembc/benchmark-runner-ml/blob/cf7c2f2634608a7c0ea7458ab7cb3379f2863424/datasets/kws01/tst_000000_Stop_7.bin)。
   其[数据说明](https://github.com/eembc/benchmark-runner-ml/blob/cf7c2f2634608a7c0ea7458ab7cb3379f2863424/datasets/README.md)
   标明Speech Commands v2、49帧×10个MFCC、INT8；
   [标签表](https://github.com/eembc/benchmark-runner-ml/blob/cf7c2f2634608a7c0ea7458ab7cb3379f2863424/datasets/kws01/y_labels.csv)
   对应Stop、标签7、共12类。
3. `tools/prepare_input.py` 下载490B样本、原始说明和标签，按原顺序解释为
   INT8，再reshape为整模型NHWC `[1,49,10,1]`，保存`.npy`。没有随机输入、
   没有重新量化，也没有把`kws_input_data.cc`直接当作目标层输入。
4. `tools/export_activations.py` 使用TensorFlow2.16.1，
   `BUILTIN_REF` resolver与`experimental_preserve_all_tensors=True`执行模型，
   实际读取tensor23 `[1,25,5,64]`。空间行优先展开为 `[125,64]`。
5. Golden仍为直接宽整数MAC及经锁定官方函数核对的INT32双舍入。先比较
   此Golden与Interpreter的tensor24全部8000个INT8，PASS后再生成RTL数据。
   Interpreter输出仅作为额外交叉核对，不替代独立Golden。
6. RTL case6运行全部125个空间位置；case7运行首个空间位置p=0。均覆盖
   阻塞与有限重叠模式。原有真实权重+合成输入case4/5保留。

整模型输入tensor0的scale=0.5847029089927673、zero-point=83；它和目标层
输入tensor23的zero-point=-128不同。不得在输入Interpreter之前对MFCC字节
使用加速器的MSB翻转规则。只有tensor23装入加速器后才按q+128处理。

## 证据文件

|文件|内容|
|---|---|
|`build/inputs/input_metadata.json`|固定提交、样本URL/标签、形状类型、变换、输入字节摘要及来源边界|
|`build/activation_metadata.json`|模型/输入/激活摘要，实际运行时版本，tensor/shape/flatten及主机8000字节比较结果|
|`build/layer_activation.npy`、`.json`|真实tensor23，中间激活8000B，范围[-128,-32]，66个不同值|
|`build/layer_interpreter_output.npy`|Interpreter tensor24，用于独立主机参考交叉核对|
|`build/activation_export.log`|实际TensorFlow执行与导出日志|
|`build/tf_install.log`、`build/tf_environment.txt`|实际安装日志及隔离环境完整pip freeze|
|`build/vectors/cases.json`|每个RTL用例的输入来源、M及激活对应关系|
|`build/simulation.log`、`build/results.csv`|最终RTL比较和任务周期|

输入字节SHA256：`ccadc642dec19c4a7f9522207ef8f1b60af7164a86894e03b68b7f5b723503e4`。
tensor23字节SHA256：`9b3d9d6ba64079304f99477cd6689a44018e7ab6987d7611d8bfc0ec3be5d81d`。
生成用例时核对激活、模型和来源记录，防止使用不匹配的旧导出。

## 复现

当前环境已安装，可从项目根目录一条命令重新执行输入准备、导出、官方
数值参考核对和完整RTL回归：

```
python tools/run.py --real-activations
```

新机器首次准备（Windows）：

```
python -m pip install --target build/deps_python -r tools/requirements-model.txt
python -m venv build/tf_env
build/tf_env/Scripts/python.exe -m pip install -r tools/requirements-runtime.txt
python tools/run.py --real-activations
```

TensorFlow2.16.1/NumPy1.26.4隔离于`build/tf_env`，模型解析环境仍使用
NumPy2.1.2。不要将`build/deps_python`加入TensorFlow进程的PYTHONPATH。
可用`--tf-python`指定另一套已安装TensorFlow2.16.1的Python。
只回归已有导出可用`python tools/run.py --model`；缺少已验证导出时不会
声称真实激活回归成功，重新导出应使用`--real-activations`。

## 范围

只使用一个已发布MFCC样本。未从原始WAV重新提取MFCC、未恢复说话人/原始
录音ID，也未重建数据集量化校准。没有据此给出整网准确率、FPGA整网运行或
真实CiM能效结论。数据保留在build用于本地验证；没有推断第三方数据的
再分发许可。最新PASS/NOT_RUN和下一项工程任务统一见`docs/STATUS.md`。
