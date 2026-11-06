# RISC-V CiM INT8 加速器 · K7 50 MHz

可综合 SystemVerilog 实现固定 K=N=64、运行时 M=1..125 的单层 INT8
pointwise 卷积。RISC-V 固件装入输入、权重、bias、逐通道 multiplier/shift 后，
一次 START 即由硬件完成全部 tile、两轮低位运算、重建、量化及最终写回。
这是 RISC-V 控制的 CiM 宏数字代理及数字外围 FPGA 原型。K7 V2.1 50 MHz
实测覆盖 M=1/125、两种调度和运行中热复位。独立 RTL 回归无需教学 SoC。
完整 K7 流程需要使用者提供授权取得的 JYDD CPU/UART 源码。
[v0.1.0 发布说明](docs/RELEASE_v0.1.md)

本分支提供可选的两层一次提交基准。两层均为 64×64 pointwise，
链式和两次 START 共用中间 SRAM 地址，在同一 K7 50 MHz 位流上
对照。[两层实测、RV32IM C 基线与复现](docs/TWO_LAYER.md)

可选的 `banked-retain` 在第一层写回时同步保留中间激活。M125
相对链式 SRAM 重读省 2,000 次共享读和 17.62 µs，增加两块
RAMB36。[同板实测与复现](docs/INTERLAYER_CACHE.md)

K7 构建默认启用请求周转与 8 KiB 双 bank 输入缓存。与 32 位回放相比，
双 bank 在同一 50 MHz 下将 M125 重叠从 26,719 降至 23,191 拍，
任务延迟减少 13.20%，缓存仍用两块 RAMB36。[双 bank 实测与逐拍归因](docs/BANKED_REPLAY.md)

独立 RTL 默认使用仅请求周转，回归可显式选择五种配置。
[共享 SRAM 四版对照](docs/SRAM_CACHE_MATRIX.md) 保留双 bank 优化前的
实测记录，原 [请求周转候选](docs/SRAM_TURNAROUND.md) 和 v0.1.0 结果分别保留。

```
运行时共享SRAM ──32bit请求/响应── 权重/参数加载与双输入槽
                                  │
                      64×16 W4数字宏代理（A4位串行）
                                  │ 16×14bit，不可暂停返回
                           两个预约原生结果槽
                                  │
                    两个8通道重建上下文 → 共享量化单元
                                  │
                        两次32bit输出写回 → sticky DONE
```

MODE=0 使用阻塞调度，MODE=1 允许两个块有限重叠。两者使用相同宏、算术
和存储端口。这里的宏是独立实现的数字代理，包含真实低位计算及4096bit
权重；不代表真实模拟宏、工艺面积或能效。

## 50 MHz 实测

2026-11-06 的四版使用同一 RV32IM 固件、输入、CPU 和 50 MHz 约束。
以下为双 bank 优化前的实板周期，四版均通过两次热复位及逐字节比较。

|构建|M1 两种模式各自|M125 阻塞|M125 重叠|RAMB36|
|---|---:|---:|---:|---:|
|baseline|4,763|78,171|56,347|16|
|turnaround|4,523|48,171|29,323|16|
|cache|4,553|51,921|30,097|18|
|combined（32 位回放）|4,523|48,171|26,719|18|

组合相对仅周转的 M125 重叠延迟少 8.88%，由 586.46 µs 降至 534.38 µs。
两个额外 RAMB36 使 M125 共享 SRAM 读从 17,216 降到 3,216 次，
访问计数来自对应 SoC 仿真。软件基线实板为 M1 23,013 拍、M125
2,749,533 拍。时序、计时窗口和证据见 [四版对照](docs/SRAM_CACHE_MATRIX.md)。

### v0.1.0 原始板测

|M|阻塞周期 / 用时|重叠周期 / 用时|每模式逐字节比较|
|---|---:|---:|---:|
|1|4,764 / 95.28 µs|4,764 / 95.28 µs|64 / 64|
|125|78,172 / 1,563.44 µs|56,348 / 1,126.96 µs|8,000 / 8,000|

同一新版 M=125 的重叠调度将任务延迟减少 **27.9179%**，速度比 **1.3873×**。
计数从 START 到最终 SRAM 写提交及 DONE，CPU 预装、结果比较和 UART 输出
均在窗口之外。单独比较量化流水化前后，50 MHz 任务周期略增，布线 WNS
由 +0.842 ns 提升至 +5.885 ns。M=125 阻塞增加 1,000 拍，重叠增加 8 拍，
M=1 两模式各增加 8 拍。2026-11-05 的原始板测中，两次热复位和随后四次任务
均通过。之后的干净构建重新执行了参考、RTL、SoC 和 Vivado 实现，生成的 FPGA
配置载荷与原板测位流逐字节相同。本次发布引用原实板记录。
[口径、时序和资源](docs/RELEASE_v0.1.md) · [UART 记录](docs/evidence/k7_uart_2026-11-05.txt)

## 快速开始

Linux / WSL 的公开回归使用 Python 3、G++ 和 Icarus Verilog（Ubuntu 24.04
验证环境使用 Icarus 12.0）。入口依次核对官方整数参考、运行宏和量化单元测试、
并比较完整算子的 INT8 输出。

```bash
python3 tools/run.py --dataset synthetic --simulator iverilog
# CI 同样覆盖最快连续接受路径
python3 tools/run.py --dataset matrix --simulator iverilog --memory fixed --variant banked
```

Windows 可使用 Python 3.12.0、G++ 9.3.0 和 Questa 2024.1。
在项目根目录设置实际工具路径。`CXX` 可省略，脚本会先查找 PATH 中的 `g++`。
首次运行需要从固定的 GitHub 上游下载官方参考函数。用合成输入快速跑完整 RTL
时只需上述依赖。

```powershell
$env:QUESTA_BIN = '<Questa 的 win64 目录>'
$env:CXX = '<g++.exe 的路径>'
python tools/run.py --simulator questa
```

复现与板测同源的真实中间激活时，先在项目内安装模型解析依赖和独立的
TensorFlow 2.16.1 环境。入口从固定模型和 MFCC 样本导出 tensor23，
完成官方整数算术核对、直接 MAC golden 生成和完整 RTL 自检。

```powershell
python -m pip install --target build/deps_python -r tools/requirements-model.txt
python -m venv build/tf_env
build/tf_env/Scripts/python.exe -m pip install -r tools/requirements-runtime.txt
python tools/run.py --real-activations --simulator questa
```

`--dataset synthetic` 是固定默认集。`--dataset model`（旧 `--model`）增加真实权重、
合成激活用例。`--dataset real` 要求已有经校验的 tensor23，`--real-activations`
先导出再执行该集。缓存存在与否不改变用例集。`--skip-official-check` 仅供
调试，终端和日志均标记 SKIPPED。输入来源见 [激活来源记录](docs/ACTIVATIONS.md)。
日志和逐任务周期保存在 `build/`。本轮四种配置各跑 22 个真实数据集任务，
每版 81,024 字节匹配，含合成和真实输入。周期由各测试的存储模型决定。

额外可执行检查：

```
python tools/synth.py --driver
python tools/synth.py
python tools/synth.py --generic
```

依次为宿主 C 驱动编译/校验、Vivado HDL analysis、与器件无关的 Yosys
综合/结构检查。`--generic` 依赖本地安装的 yowasp-yosys；具体版本和安装
方法见 [接入说明](docs/INTEGRATION.md)。未知 part 时不会自动选择器件。
目标 FPGA 综合/布局布线入口在 `fpga/`，必须传真实 part、时钟和板级约束。

## 板级复现与设计说明

- [板级构建与演示](docs/BOARD_K7.md) 包含 JYDD 依赖清单、固件与 SoC 入口、
  JTAG/UART 演示和旧基线恢复方法。
- [设计讲解](docs/DESIGN_WALKTHROUGH.md) 包含低位重建、容量预约、写回生命周期、
  双舍入和两种模式的量化流水周期分析。
- [v0.1 发布说明](docs/RELEASE_v0.1.md) 包含源码/位流对应、干净目录复现、
  资源与时序以及公开发布的具体前置条件。

## 关键文件

|文件|作用|
|---|---|
|`rtl/cim_accel.sv`|MMIO、加载、阻塞/重叠调度、容量预约、重建和写回|
|`rtl/cim_macro.sv`|64行、16个W4列的实际位串行宏代理|
|`rtl/requant.sv`|INT32双舍入、输出零点和饱和|
|`tb/tb_accel.sv`|最终INT8逐元素比较及合法等待、状态寿命检查|
|`tb/tb_units.sv`|宏时序、符号边界与量化内部舍入检查|
|`tools/reference.py`|独立直接MAC与数据布局生成|
|`tools/check_reference.py`|Python与锁定官方C++整数运算交叉核对|
|`tools/prepare_input.py`、`tools/export_activations.py`|固定真实模型输入、来源记录、实际中间张量导出及主机比较|
|`sw/cim.h`, `sw/cim.c`, `sw/example.c`|寄存器、参数校验、打包及裸机调用|

[逐拍合同与容量说明](docs/ARCHITECTURE.md) 解释数据流、位宽和状态寿命。
[软件与 FPGA 接入](docs/INTEGRATION.md) 给出 MMIO、内存可见性和复位要求。
工程规格及来源保留在 [codex_handoff](codex_handoff/)。
固定数值依赖、模型与许可记录见 [第三方来源](docs/THIRD_PARTY.md)。

数值锁定到 TensorFlow v2.16.1 的
[INT32 双舍入实现](https://github.com/tensorflow/tensorflow/blob/v2.16.1/tensorflow/lite/kernels/internal/common.cc)。
输入零点固定-128，低/高输入 nibble 均为 U4，权重低 nibble 为 U4、高 nibble
为 S4；bias 只加一次。支持 multiplier>=0、shift∈[-31,0]，参数准备和驱动
检查完整输入范围内 INT32 不溢出。Golden 不使用 RTL 的四项分解。

当前测试输入及真实中间激活的证据边界、实际工具版本、运行结果与下一项
任务统一维护在 [docs/STATUS.md](docs/STATUS.md)。没有把总线测试平台称为
真实 CPU 执行，也没有把单层验证称为完整 KWS 推理。

## 许可证

获授权的项目原创代码采用 [Apache-2.0](LICENSE)。第三方代码、模型和数据
各自适用其原条款。发布源码包含原创板级适配，外部 CPU/UART、生成的 CPU
副本和整板位流均由有权使用者在本地提供或生成。[第三方说明](docs/THIRD_PARTY.md)
