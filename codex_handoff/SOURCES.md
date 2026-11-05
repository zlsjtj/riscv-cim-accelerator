# 参考资料与证据状态

更新时间：2026-11-04。
这是实施前的参考资料记录。实际激活导出与证据见 [ACTIVATIONS.md](../docs/ACTIVATIONS.md)，发布范围及第三方依赖见 [THIRD_PARTY.md](../docs/THIRD_PARTY.md)。当前交接包没有复制第三方 RTL 或模型文件。

## 1. 固定真实工作负载

MLCommons Tiny：
https://github.com/mlcommons/tiny

选定提交：
4addd0fa08d216e20637637874e084895f289da4

KWS模型：
https://github.com/mlcommons/tiny/blob/4addd0fa08d216e20637637874e084895f289da4/benchmark/training/keyword_spotting/trained_models/kws_ref_model.tflite

原始文件下载地址：
https://raw.githubusercontent.com/mlcommons/tiny/4addd0fa08d216e20637637874e084895f289da4/benchmark/training/keyword_spotting/trained_models/kws_ref_model.tflite

对应模型结构：
https://github.com/mlcommons/tiny/blob/4addd0fa08d216e20637637874e084895f289da4/benchmark/training/keyword_spotting/keras_model.py

证据：此前已读取这个53936B模型，提取了目标层metadata、weights、bias，静态区间见CIM_SPEC.md。接收此包的新Codex会话没有自动获得旧会话临时文件，需按链接获取或使用用户提供的同版本文件。
实施前尚未导出真实中间激活。v0.1.0 的真实 tensor23 由固定模型和 MFCC 样本重新导出，出处见上述激活记录。

## 2. 数值参考

LiteRT INT8规范：
https://developers.google.com/edge/litert/conversion/tensorflow/quantization/quantization_spec

TensorFlow v2.16.1 reference integer Conv：
https://github.com/tensorflow/tensorflow/blob/v2.16.1/tensorflow/lite/kernels/internal/reference/integer_ops/conv.h

整数舍入实现：
https://github.com/tensorflow/tensorflow/blob/v2.16.1/tensorflow/lite/kernels/internal/common.cc

量化参数生成：
https://github.com/tensorflow/tensorflow/blob/v2.16.1/tensorflow/lite/kernels/internal/quantization_util.cc

Conv参数准备：
https://github.com/tensorflow/tensorflow/blob/v2.16.1/tensorflow/lite/kernels/kernel_util.cc

gemmlowp基础整数运算：
https://github.com/google/gemmlowp/blob/master/fixedpoint/fixedpoint.h
实现时优先跟随所选TensorFlow版本锁定的依赖版本，不能使用会漂移的master作为最终可复现版本。

Interpreter中间张量：
https://developers.google.com/edge/api/tflite/python/tf/lite/Interpreter
可使用preserve-all-tensors和适当reference resolver导出中间输入；golden仍以已锁定的舍入合同为准，不能默认不同优化后端逐位相同。

## 3. 宏约束参考

OpenC2论文：
https://zyh0911.github.io/assets/pdf/OpenC2.pdf
DATE 2025，DOI：10.23919/DATE64628.2025.10993122。

仓库：
https://github.com/OpenC2-official/OpenC2_V1.0

已检查的提交：
df0af784a8a56388cee1a5dce6660b7aa4516692

固定W4A4实例：
https://github.com/OpenC2-official/OpenC2_V1.0/blob/df0af784a8a56388cee1a5dce6660b7aa4516692/results/dcim_macro_64x64_for_4bitx4bit/frontend/verilog_file/top_module/dcim_macro_64x64_for_4bitx4bit.v

控制模板：
https://github.com/OpenC2-official/OpenC2_V1.0/blob/df0af784a8a56388cee1a5dce6660b7aa4516692/library/verilog/control_rtl.v

单元库：
https://github.com/OpenC2-official/OpenC2_V1.0/blob/df0af784a8a56388cee1a5dce6660b7aa4516692/library/verilog/std_cell_lib.v

已知事实：
- 选定实例为64行、64物理位列、16个W4输出、A4位串行、14bit原生输出。
- 每列独立weight sign，global input sign；原生宏内部已经有shift/accumulate。
- 启动后的计算不提供下游pause/ready。
- 正负半拍和输出时钟须在FPGA代理中明确表达。
- 所查库的dcim_bitcell、sram_rw、dff存在空body。
- 此前未见明确仓库LICENSE，不能据“GitHub公开”就把整个RTL复制后重新许可。
- “约7个宏周期”来自静态控制分析，未完成原始cell模型闭合验证。

使用方式：参考公开行为和接口约束，独立实现可综合代理，记录相同点与差异。无需将该仓库变成本项目依赖。OpenC2编译器可以生成其他位宽；W4是本项目所选固定实例的约束。

## 4. 数据通路与方法参考

SNAX streamer：
https://kuleuven-micas.github.io/snax_cluster/tutorial/streamer_design.html
参考有限FIFO、地址生成、没有ready的返回通道需要提前预留空间；不移植整套集群。

Gemmini：
https://github.com/ucb-bar/gemmini
参考load/execute/store职责与硬件tile循环；不把完整Chipyard平台纳入首版。

FLEX-CIM（原始研究兴趣来源）：
FLEX-CIM: A Flexible Kernel Size 1-GHz 181.6-TOPS/W 25.63-TOPS/mm² Analog Compute-in-Memory Macro
IEEE JSSC，2024，59(9)，3021–3031。
DOI：https://doi.org/10.1109/JSSC.2024.3386192
本项目定位是CiM数字执行/外围FPGA工程，不宣称复现该模拟宏或其测量结果。

## 5. FPGA方法

AMD时序签核：
https://docs.amd.com/r/en-US/ug906-vivado-design-analysis/Verifying-Timing-Signoff

AMD时钟使能建议：
https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/Using-Gated-Clocks

以实际Vivado版本与目标器件的文档为准。FPGA part、时钟、XDC及现有RISC-V工程需要真实资料；此前尚未核实具体型号。

## 6. Codex工作方式

项目指令：
https://learn.chatgpt.com/docs/agent-configuration/agents-md

分阶段工作流：
https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex

官方说明AGENTS.md会作为项目指导读取；CIM_SPEC.md、SOURCES.md、STATUS.md是本项目约定，需要启动提示词/AGENTS显式引导读取。
不需要改全局权限、指定未经核实的CLI参数，或为本项目额外构建复杂agent框架。

## 7. 数据与结果的表述

可以作为已核对背景：模型元数据、静态范围、公开代码可读接口。
必须由实现环境重新生成：测试PASS、RTL波形、真实中间输入导出、综合资源、布线后时序、板上运行周期。
源文件版本与许可证通过仓库提交、下载来源与记录管理即可，不要求新增哈希验收系统。
