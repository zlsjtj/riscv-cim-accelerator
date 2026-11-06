# 两层 INT8 pointwise 一次提交

两层均为 K=N=64，运行时共享 M 和调度 MODE。基于
`upgrade/banked-cache` 的双 bank 输入回放。链式、CPU 两次 START
和纯 RV32IM C 三条路径由同一个固件在同一个 SoC 位流上执行。
两条硬件路径的实测均使用重叠模式（MODE=1）。

## 层间合同

第一层的输出采用原有定点双舍入及 INT8 饱和，零点为 −128。它按
行优先排列，每个空间位置连续存放 64 个通道。第二层直接按相同
INT8 布局和零点读取。两条硬件路径和 C 路径都把中间结果写入
`0x80106000`，最终输出写入 `0x80108000`。

|MMIO 偏移|用途|
|---|---|
|`0x00` 位 0|START|
|`0x00` 位 1|ACK_DONE|
|`0x00` 位 2|和 START 一起写入时执行两层|
|`0x2c`|第二层权重基址|
|`0x30`|第二层参数基址|
|`0x34`|第二层输出基址|

接受 START 时锁存两层配置。第二层输入由第一层输出地址推导，
驱动检查两层地址范围和布局约束。第一层最后一字提交且上下文、
宏结果、量化和存储请求排空后，硬件从第二层 tile 0 启动，重新
填充本地输入缓存。BUSY 跨层连续，DONE 只在第二层写完并排空后
置位。链式模式的核计数覆盖两层。

## Golden 和计时

第一层使用已核验的 MLCommons tensor23 和该层真实权重、量化参数。
第二层是固定种子 `0xc1a00264` 的合成层。独立 Python 参考用完整
INT8 权重和直接 MAC 生成第一层 golden，将其解码成有符号 INT8，
再生成第二层 golden。固件在每次任务前用两个 golden 的按位反码
预填输出区，停表后分别逐字节检查中间与最终输出。M1 使用 M125
的第一行。[真实激活来源](ACTIVATIONS.md)

三条路径使用同一个 SoC 硬件计时器。起点是输入、权重和输出预填均
就绪后的计时器启动 MMIO 提交沿。窗口内执行提交及轮询，或两次
RV32IM C 算子调用。终点是 CPU 读过最终输出的最后一个字后，计时器
停止 MMIO 的提交沿。停表前的可见性读及停表指令计入窗口。golden
比较及 UART 均在窗口外。

## SoC 仿真

|M|CPU 两次 START|链式一次 START|两层 RV32IM C|
|---|---:|---:|---:|
|1|9,765 拍|9,601 拍|46,001 拍|
|125|47,204 拍|47,052 拍|5,493,594 拍|

Questa 2024.1 确认三条路径分别有 2、1、0 次 START 和同样次数的
DONE。两个结果区域均完整提交，第二层读中间 SRAM 前第一层已全部提交。
停表前 CPU 已发出对最终区域最后一个字的读。M125 两条硬件路径均
接受 6,432 次共享读、提交 4,000 次共享写。两次 START 的核内周期
合计为 46,385 拍，链式为 46,381 拍。逐拍数据显示共享端口背压从
9 拍降为 5 拍。完整窗口少 152 拍，其中 148 拍来自核窗口之外的
提交、轮询及可见性读路径。M1 对应完整窗口少 164 拍，核内少 4 拍。

定向控制验证覆盖第二层地址不对齐、BUSY 期间改写第二层影子配置、
第一层写完时保持 BUSY、以及第二层读响应在途时同步复位。原单层
真实激活可变等待回归也通过 22 项任务，常规板级固件入口的单层 SoC
仿真通过普通 START、运行中热复位及重提。

## K7 50 MHz 实现

Vivado 2023.2 在 `xc7k325tffg900-2` 上布线通过。整板使用
16,459 LUT、11,244 FF、18 RAMB36 和 8 DSP，其中输入缓存用两个
RAMB36。WNS/WHS 为 +7.019/+0.029 ns。内部未约束端点、路由错误、
DRC Error 和 `REQP-1839` 均为 0。20 条 DRC 建议来自 DSP 流水。
最长 setup 数据路径是量化乘积寄存器到输出字节寄存器，耗时 12.784 ns。

## 同板实测

2026-11-06 在同一 K7 V2.1 两次易失加载同一位流 `43494d45`。
六组端到端周期在两次实测及 SoC 仿真中逐项一致。每次实测共核对
48,384 个 INT8 字节，涵盖两种 M、三条路径的中间与最终输出，零失配。

|M|CPU 两次 START|链式一次 START|两层 RV32IM C|一次提交少用时间|
|---|---:|---:|---:|---:|
|1|9,765 拍 / 195.30 µs|9,601 拍 / 192.02 µs|46,001 拍 / 920.02 µs|164 拍 / 3.28 µs（1.68%）|
|125|47,204 拍 / 944.08 µs|47,052 拍 / 941.04 µs|5,493,594 拍 / 109.87188 ms|152 拍 / 3.04 µs（0.32%）|

两次 START 和一次 START 运行相同的两次算子计算，并使用相同的
中间 SRAM 地址。一次提交的主要收益是省下 CPU 在两层之间的控制路径。
记录的输入、权重、参数、两级 golden、固件和位流摘要可对应到源码
`f842880`。[两次原始 UART、逐拍摘要、对照 CSV 和布线证据](evidence/two_layer_2026-11-06/)

## 复现

先按 [板级构建流程](BOARD_K7.md) 配置本机 CPU/UART、Vivado、
Questa 和 RV32 GCC，并准备经来源校验的真实激活。

```powershell
python tools/run.py --simulator questa --dataset real --variant banked
python tools/k7.py prepare --two-layer --cpu-source $cpuSrc --gcc-bin $rvBin
python tools/k7.py sim --two-layer --profile-tasks --cpu-source $cpuSrc
python tools/k7.py impl --two-layer --cpu-source $cpuSrc
python tools/k7.py program --two-layer --jtag $jtagSerial --port $serialPort
python tools/k7.py program --two-layer --bitstream build/k7_two_layer/cim_k7.bit --out build/k7_two_layer_repeat --jtag $jtagSerial --port $serialPort
```

默认输出目录为 `build/k7_two_layer/`。UART `CHAIN_RESULT` 各字段为
路径编号、M、窗口周期、每层输出字节数、中间失配数、最终失配数及
驱动状态，使用十六进制。路径 0 为 CPU 两次 START，1 为链式一次
START，2 为两层 RV32IM C。
