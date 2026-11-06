# 真实 KWS PW(op2) → CPU DW(op3) → PW(op4)

本分支从 `v0.3.0` 建立。两种路径共用同一 RV32IM ELF、模型
参数、输入、布局和 DW 函数。混合路径对两个 PW 各提交一次
MODE1 START，纯 CPU 路径复用现有八输出展开的 RV32IM PW。
CiM RTL 沿用 v0.3.0。K7 使用 `banked` 输入缓存，每个 PW 是独立
任务。Ibex 沿用开放整机的加速器配置。

```text
输入备份 tensor23 → A → PW(op2) → B(tensor24)
                                  ↓ CPU DW(op3)
                     A(tensor25) ←┘
                     A → PW(op4) → B(tensor26)
```

两路运行开始前恢复 A，并把 B 写成最终 golden 的逐位反码。
DW 从 B 取实际 PW1 输出，PW2 从 A 取实际 DW 输出。运行时 SRAM
镜像只放 tensor23 和最终 tensor26 golden。tensor24/25 golden
保留在宿主机，供诊断比较。

## 来源和数值合同

模型来自 MLCommons Tiny `4addd0fa08d216e20637637874e084895f289da4`。
两个已发布量化 MFCC 输入来自 EEMBC
`cf7c2f2634608a7c0ea7458ab7cb3379f2863424` 的 Stop 和 Left。
每个输入 490 字节，按发布顺序解释成 `[1,49,10,1]` INT8。
依赖源、哈希及许可沿用 [第三方记录](THIRD_PARTY.md)。

TensorFlow 2.16.1 单线程 `BUILTIN_REF` 导出 tensor23–26，形状
均为 `[1,25,5,64]`。独立整数参考从 tensor23 做顺序 MAC，
比较后继续使用自身输出。op3 是 stride/dilation 1、SAME、
depth multiplier 1 的 3×3 depthwise。两个 PW 都是 64×64。
三层激活零点均为 −128、权重零点为 0、融合 ReLU，逐通道量化
使用 INT32 双舍入。每个样本比较 24,000 字节。

## SRAM 布局

下表为相对数据区基址的偏移。K7 基址 `0x80100000`，Ibex
fixture 基址 `0x00110000`。Ibex 的栈位于 fixture 之外。

|区段|偏移|字节|
|---|---:|---:|
|K7 固件 data/bss 保留|0x0000|1,024|
|K7 栈保留|0x0400|3,072|
|工作区 A|0x1000|8,000|
|PW1 / PW2 权重|0x3000 / 0x4000|各 4,096|
|PW1 / PW2 参数|0x5000 / 0x5400|各 768|
|DW 权重 / 参数|0x5800 / 0x5c00|576 / 768|
|工作区 B|0x6000|8,000|
|Stop 输入 / 最终 golden|0x8000 / 0xa000|各 8,000|
|Left 输入 / 最终 golden|0xc000 / 0xe000|各 8,000|

已分配及保留 63,168 字节，64 KiB 内剩 2,368 字节间隙，最高
数据地址为偏移 `0xff3f`。PW 权重按
tile、K、lane 排列，DW 权重按 ky、kx、channel 排列。参数为
64 组三个小端 int32（bias、multiplier、shift）。K7 另有 16 KiB
指令 ROM，链接器约束 ROM 大小和 data/bss 边界。
实测固件 ELF 的 `.text/.data/.bss` 为 5,880/144/0 字节。
该 ELF 的 GCC `.su` 和反汇编显示，最深调用链为
`main → timed → pointwise → cim_sw_pointwise`，静态合计 320 字节。

## 计时和诊断

每次计时从数据恢复完毕后读定时器，到 CPU 读取最终输出末字后
读定时器。PW1、DW、PW2 分别在该段的末字读取后采样。总周期是
三段之和，涵盖提交、轮询和数据交接，比较和字符输出在窗口外。
Ibex 读取 `mtime`，K7 读取 SoC 周期计数器。PW 核内周期另从
加速器 `CYCLES` 读取。

`--diagnostic` 在四个正式计时窗口全部结束后，重新运行两样本
两路径。固件从实际 A/B 读出 tensor24/25/26，按 128 字节分片
输出，宿主检查顺序、长度、逐字节结果和 SHA-256，再写出原始
`.bin`。省略该选项时，固件只打印计时及最终 golden 失配数。

## Ibex RTL 仿真

以下四行来自同一个 GCC 13.2.0 ELF、Ibex `2373e5d` 和
Verilator 5.020。单位为仿真时钟周期。

|样本|路径|PW1|CPU DW|PW2|总周期|
|---|---|---:|---:|---:|---:|
|Stop|混合|23,964|1,030,464|23,972|1,078,400|
|Stop|纯 CPU|3,892,575|1,030,464|3,893,727|8,816,766|
|Left|混合|23,964|1,030,830|23,972|1,078,766|
|Left|纯 CPU|3,892,608|1,030,830|3,893,848|8,817,286|

两次计时混合任务的每个 PW 核内均为 23,427 拍。四个计时结果
每个比较 8,000 个最终字节。独立诊断捕获两路径、两样本的
tensor24/25/26，共 96,000 字节零失配。包含诊断在内，硬件观测
8 次 START、8 次 DONE、25,728 个共享读字及 16,000 个写字。
[Ibex 结果](evidence/kws_subgraph/ibex.json) ·
[执行摘要](evidence/kws_subgraph/ibex_execution.txt)

另用省略 `--diagnostic` 的计时专用 ELF 运行两样本两路径。
四个窗口只在 PW2 各少 1 拍，仍各比较 8,000 个最终字节，
硬件观测 4 次 START 和 DONE。
[计时专用 ELF 结果](evidence/kws_subgraph/ibex_timing_only.json)

### 工具链对照

Stop 的四个导出张量和六段打包常量逐字节复现了交接包。用同一
Ibex RTL 和当前 Verilator 5.020 原样重放附件的 GCC 12.2.0
ELF，两路径各段周期及整个仿真的 10,910,935 周期均与附件
Verilator 5.032 的记录相同。用 GCC 13.2.0 / binutils 2.42 重编同一附件源码、
链接脚本和 fixture 后，混合路径 DW 增加 9.91%。集成源码在
同一 GCC 13.2.0 上生成的 DW 比该重编对照低
10.76%，两次 CPU PW 的周期各只差 20/24 拍。

|Stop Ibex 对照|混合 DW|混合总周期|纯 CPU 总周期|
|---|---:|---:|---:|
|附件原 ELF，用 Verilator 5.020 重放|1,050,571|1,098,468|8,824,807|
|附件源码，用 GCC 13.2.0 重编|1,154,703|1,202,613|8,940,961|
|本轮集成版，用 GCC 13.2.0|1,030,464|1,078,400|8,816,766|

K7 使用本机 xPack GCC 15.2.0 和 JYDD CPU。两平台的 CPU 执行、
总线和编译器共同影响周期。K7 编译的纯 CPU PW 内核段与 v0.3.0
用同一编译器和 flags 编译时的机器码一致。
[对照原始计时与源码哈希](evidence/kws_subgraph/toolchain_control.json)

## K7 50 MHz 实测

2026-11-07，在原 `xc7k325tffg900-2` K7 上加载并读回
`43494d4a`。四个正式窗口与独立诊断共用一个位流、一个
xPack GCC 15.2.0 固件和一份 SRAM 镜像。

|样本|路径|PW1（拍）|CPU DW（拍）|PW2（拍）|总周期|毫秒|
|---|---|---:|---:|---:|---:|---:|
|Stop|混合|23,627|886,686|23,626|933,939|18.67878|
|Stop|纯 CPU|2,749,550|886,728|2,748,866|6,385,144|127.70288|
|Left|混合|23,630|886,971|23,632|934,233|18.68466|
|Left|纯 CPU|2,749,613|886,974|2,748,096|6,384,683|127.69366|

四个正式窗口各比较 8,000 个最终字节，零失配。独立诊断从
UART 恢复 12 个 tensor24/25/26，共 96,000 字节，与 TensorFlow
逐字节一致。两样本混合路径的两个 PW 核内均为 23,191 拍。
相比同一固件的 Questa SoC 仿真，板上混合 PW1 窗口各多 3 拍，
核内、DW、PW2 和纯 CPU 窗口一致。该差值未定位到单个事件。

同位流对应的 SoC 握手验证每个混合计时窗口有两次 START、两次
DONE、6,432 次共享 SRAM 读及 4,000 次写，CPU DW 在两次 START
之间写入 8,000 个字节。纯 CPU 窗口观测到两段各 2,000 个 CPU
PW 写字，DW 写入 8,000 字节。
[板测结果](evidence/kws_subgraph/k7_board.json) ·
[UART 计时节选](evidence/kws_subgraph/k7_board_uart.txt) ·
[SoC 事件摘要](evidence/kws_subgraph/k7_soc_execution.txt)

20 ns 布线通过，WNS/WHS 为 +7.025/+0.082 ns。整板 16,287 LUT、
11,237 FF、18 RAMB36、8 DSP。路由错误、内部未约束端点、
DRC Error 及 `REQP-1839` 均为 0。首次 Vivado 运行在布线后写
签核报告时中断，从原综合 DCP 恢复并完成同一物理流程与签核。
原始报告、routed DCP 及 UART 完整分片保存在
`build/k7_kws_diag/`。[位流、ELF、镜像和报告哈希](evidence/kws_subgraph/k7_build.json)

## 端到端瓶颈

K7 两样本的纯 CPU／混合延迟比分别为 6.8368× 和 6.8341×，延迟约
降低 85.37%。CPU DW 占两样本混合总周期的 94.94%，两段 PW
合计仅占 5.06%。Ibex 混合路径的 DW 占 95.55% 左右。

下一轮可先优化 CPU DW 的内层循环。将 SAME 边界判定提到空间
位置层，并一次处理四个相邻通道，目标把 K7 DW 从约 887,000
降到 710,000 拍以内。按现有 PW 周期估算，DW 降 20% 可省约
177,000 拍（3.55 ms），端到端约 15.13–15.14 ms，降幅约 19%。
按每个样本 60,736 个有效 tap×channel 计算，DW 段的目标从约
14.6 降到 11.7 拍/有效 MAC，含量化和交接。以相同两样本、
编译器和计时窗口复核该目标。

## 复现

用 Python 3.12 安装 `tools/requirements-runtime.txt`，在 TensorFlow
环境执行参考准备。模型、原始样本和张量留在忽略目录。

```bash
python tools/prepare_kws.py
```

Linux / WSL 的依赖与版本见 [Ibex 整机](IBEX.md)。`--trace` 可另
启用长指令轨迹。

```bash
python3 tools/run_ibex.py --kws build/kws_fixture
python3 tools/run_ibex.py --kws build/kws_fixture --diagnostic
```

K7 使用 [板级依赖](BOARD_K7.md)。以下四步共用一个输出目录和
同一份固件、SRAM 镜像。板上保存原始 UART 记录。

```powershell
python tools/k7.py prepare --kws build/kws_fixture --diagnostic --cpu-source $cpuSrc --gcc-bin $rvBin
python tools/k7.py sim --kws build/kws_fixture --diagnostic --cpu-source $cpuSrc
python tools/k7.py impl --kws build/kws_fixture --diagnostic --cpu-source $cpuSrc
python tools/k7.py program --kws build/kws_fixture --diagnostic --jtag $jtagSerial --port $serialPort
```

这是固定模型的三算子应用验证。来源覆盖已量化 MFCC 到子图的
实际激活及三段输出，指标口径为两个固定样本的子图结果。
