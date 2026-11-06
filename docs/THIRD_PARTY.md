# 固定来源与许可

没有复制 OpenC2 第三方 RTL。`rtl/` 的数字宏代理、调度与量化均为本项目
独立实现。公开接口约束来源保留在 `codex_handoff/SOURCES.md`。根目录
[LICENSE](../LICENSE) 的 Apache-2.0 仅适用于本项目有权许可的原创内容。
外部代码、模型、数据和工具沿用各自的许可或授权。

|依赖|固定版本/用途|来源与许可|
|---|---|---|
|MLCommons Tiny|`4addd0fa08d216e20637637874e084895f289da4`，KWS模型常量|[固定模型](https://github.com/mlcommons/tiny/blob/4addd0fa08d216e20637637874e084895f289da4/benchmark/training/keyword_spotting/trained_models/kws_ref_model.tflite)，仓库[Apache-2.0](https://github.com/mlcommons/tiny/blob/4addd0fa08d216e20637637874e084895f289da4/LICENSE.md)|
|TensorFlow|v2.16.1，INT32双舍入与QuantizeMultiplier原函数|[common.cc](https://github.com/tensorflow/tensorflow/blob/v2.16.1/tensorflow/lite/kernels/internal/common.cc)、[quantization_util.cc](https://github.com/tensorflow/tensorflow/blob/v2.16.1/tensorflow/lite/kernels/internal/quantization_util.cc)，Apache-2.0|
|gemmlowp|`16e8662c34917be0065110bfcd9cc27d30f52fdf`，TF所锁定的整数底层|[fixedpoint.h](https://github.com/google/gemmlowp/blob/16e8662c34917be0065110bfcd9cc27d30f52fdf/fixedpoint/fixedpoint.h)，Apache-2.0|
|tflite schema parser|2.18.0，仅解析FlatBuffers|[项目](https://github.com/zhenhuaw-me/tflite)，Apache-2.0；不作为推理运行时|
|numpy / flatbuffers|2.1.2 / 25.12.19，模型解析|构建依赖，版本锁定见`tools/requirements-model.txt`；BSD-3-Clause / Apache-2.0|
|TensorFlow runtime / NumPy|2.16.1 / 1.26.4，隔离环境实际中间激活导出|`build/tf_env`，Apache-2.0 / BSD-3-Clause；安装版本全表见`build/tf_environment.txt`|
|EEMBC KWS 样本|`cf7c2f2634608a7c0ea7458ab7cb3379f2863424`，490 B 已发布 MFCC|`prepare_input.py` 直接从固定提交获取。该提交的根目录及 `datasets/` 树未发现 LICENSE/COPYING/NOTICE 文件，数据 README 给出了来源和格式，样本的再分发许可仍未核实。[固定样本与来源](ACTIVATIONS.md)|
|JYDD CPU 与 UART|既有本地工程的 `route_src/myCPU.sv`、`route_src/uart.sv` 和 `common/` 依赖|原件 SHA-256 见 [清单](V0.1_MANIFEST.json)。`--cpu-source` 从用户授权取得的工程中读取。未发现可核实的公开源码获取途径或再分发许可。同步复位改动仅生成在 `build/` 副本中。|
|竞业达 K7 V2.1 板级资料|用户提供的原理图、教学 XPR 和 XDC|仅记录已核对的器件和引脚约束，原资料留在本地。[板级说明](BOARD_K7.md)|
|xPack GNU RISC-V Embedded GCC|15.2.0-1，RV32I/ILP32 编译及 objcopy|本机构建工具，编译和许可信息见 [xPack 发布页](https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/tag/v15.2.0-1)，构建入口使用外部安装。|
|pyserial|3.5，板测串口采集|PyPI 安装，[BSD-3-Clause](https://pypi.org/project/pyserial/3.5/)，RTL 和 SoC 仿真无需安装。|
|lowRISC Ibex Simple System|固定 `2373e5dadcfc4f56672962fa242f6a051acc9aca`，RV32IM RTL 整机仿真|[上游源码及许可](https://github.com/lowRISC/ibex/tree/2373e5dadcfc4f56672962fa242f6a051acc9aca)，Ibex 为 Apache-2.0，vendored 组件保留上游许可。构建时下载到 `build/`，提交的小型接入补丁适用所修改文件的上游 Apache-2.0 条款。|
|Verilator / GNU RISC-V GCC / FuseSoC / Edalize|5.020 / 13.2.0 / 2.4.3 / 0.6.1，开放整机工具链|[Verilator 许可](https://verilator.org/guide/latest/license.html)、[GCC 许可](https://gcc.gnu.org/onlinedocs/libstdc++/manual/license.html)、[FuseSoC](https://github.com/olofk/fusesoc)、[Edalize](https://github.com/olofk/edalize)。按 [整机说明](IBEX.md) 安装，未复制工具二进制。|

模型、官方头文件和下载的参考原文件只保存在 `build/deps/`。测试时从固定
TensorFlow原文件摘取两个函数编译，小封装不构建整个TensorFlow仓库；生成
的include保留版权/许可头。原始许可另存 `build/deps/tiny_LICENSE`、
`gemmlowp_LICENSE`、`tensorflow_LICENSE`。Python golden先与实际官方函数
比较，再参与RTL输出比较，不将纯Python结果作为RTL证据。

Yosys WASM依赖的版本/许可及综合边界见`docs/INTEGRATION.md`。Questa、
Vivado及其附带GCC使用本机已有安装，没有将其二进制复制进项目源码。

公开源码范围为项目原创 `rtl/`、`tb/`、`sw/`、`fpga/`、`tools/`、
README、规格、交付文档及精选文本证据。`build/`、外部 CPU/UART、生成副本、板卡原资料、
下载的上游样本、导出的张量与黄金数据均作为本地输入或产物保留。现有
整板 bit/DCP 包含外部逻辑，位流还初始化了测试数据，均排除在 v0.1.0 之外。
板测数字、来源、报告位置和校验摘要可在交付文档中核对。
