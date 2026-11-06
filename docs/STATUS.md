# 实际状态与续接

## 真实 KWS 三算子子图

`upgrade/kws-real-subgraph` 基于 v0.3.0。已用 TensorFlow 2.16.1
和独立顺序 MAC 核对 Stop、Left 两个样本的 48,000 个输出字节。
复用一次 START 的独立 PW，在两个 PW 之间由 CPU 执行真实 DW。

源码 `a37a911` 的同 ELF 混合和纯 CPU 模式在 Ibex、K7 SoC
仿真及 K7 50 MHz 上均通过。三个环境各在独立诊断中比较
96,000 个中间及最终字节，零失配。Ibex 计时专用 ELF 的
Stop/Left 混合周期为 1,078,399/1,078,765，纯 CPU 为
8,816,765/8,817,285。

2026-11-07，原 K7 同一位流 `43494d4a` 上，Stop/Left 混合为
933,939/934,233 拍，纯 CPU 为 6,385,144/6,384,683 拍。
板上读回已核对，20 ns WNS/WHS 为 +7.025/+0.082 ns。
本轮 K7 验证无剩余阻断。下一项为 CPU DW 内层循环，K7 实测
占混合窗口 94.94%，以 710,000 拍以内作为下一轮评估目标。
[逐阶段结果、内存布局、工具链对照和复现命令](KWS_SUBGRAPH.md)

## v0.3.0 与开放 Ibex 整机

稳定版采用 `banked-early-write` 双层调度作为 K7 推荐复现配置。
`777c941` 对应位流 `43494d48`，`3c91e8a` 封存同一固件的六路径
对照。核验了本地 bit/ELF/SRAM 镜像和 UART 的哈希与记录，也用
原始 tensor23 重新生成并核对两层输入与 golden 哈希。M125 从
CPU 两次 START 的 47,197 拍降到 39,730 拍，累计 15.82%。
[完整板测](TWO_LAYER_COMPARISON.md)

Ibex Simple System 固定在 `2373e5d`，通过公开 Verilator
工具链执行 RV32IM 裸机程序。Ubuntu 24.04 上运行
`python3 tools/run_ibex.py` 和 `python3 tools/run_ibex.py --m 125`
均通过，单次接受 START 后两级输出分别各 64/8,000 字节零失配。
端到端分别 9,898/40,189 拍，核内 9,033/39,338 拍。CI 使用 M1
入口，两种独立 RTL 回归仍保留。
[依赖、架构与执行证据](IBEX.md) · [发布说明](RELEASE_v0.3.0.md)

开放整机所需依赖均有公开获取路径。K7 构建使用授权取得的 JYDD
源码、Vivado 和实板。若继续做调度优化，以本节归档的同配置板测
为基线，复用此前的逐拍分析入口。

## 第二层量化与写回重叠

`upgrade/interlayer-writeback-schedule` 从 `4665433` 建立，源码
`777c941`。M125 第二层首 tile 的 389 个其余周期中，252 拍归
写请求生成或提交，124 拍归上下文分配，10 拍归量化，3 拍归宏返回、
重建和退出。共享 SRAM 无背压。第二层低字可在高字量化完成前写回，
末字实际提交可同拍安装已填完的预取行。

Questa 定向背压、复位、22 项单层真实数据与完整两层 SoC golden
通过。M125 首 tile 其余周期从 389 降到 201，末宏后排空从 16
降到 14。核内 M1 从 8,923 降到 8,907 拍，M125 从 40,543 降到
39,039 拍。两条路径的共享 SRAM 读/写分别为 M1 的 2,448/32
及 M125 的 4,432/4,000 个 32 位字，来自 SoC 握手计数。

2026-11-06，原 K7 50 MHz 同位流 `43494d48` 上的 M1/M125 两层
INT8 golden 全部通过。M1 端到端 9,611 → 9,606 拍，M125
41,231 → 39,730 拍（824.62 → 794.60 µs，减少 3.64%）。
整板 16,376 LUT、11,233 FF、20 RAMB36、8 DSP，WNS/WHS 为
+6.071/+0.085 ns，当时板上的易失位流为 `43494d48`。
[逐拍分析、板测证据及复现命令](INTERLAYER_WRITEBACK.md)

本轮 K7 验证无外部阻断。若继续降低第二层延迟，下一项是核对剩余
201 拍中高字量化返回到请求登记的控制边界，再比较可缩短的周期与
量化关键路径的时序代价。

## 第二层提前回放

`upgrade/interlayer-replay-schedule` 从 `upgrade/interlayer-cache`
建立。源码 `4927a29` 在旧行完成宏输入采样后复用输入槽，在旧行
末字写提交和新行回放返回排空后才放行新行。M125 第二层首 tile
输入等待从 630 降到 10 拍，末宏后的排空仍为 16 拍，完整核窗口
少 4,960 拍。定向背压与复位、完整 SoC 仿真及 22 项单层真实数据
回归通过。

2026-11-06，K7 50 MHz 同位流 `43494d47` 的 M1/M125 中间和最终
INT8 均逐字节匹配独立 golden。相对片上保留，M125 端到端从
46,176 拍降到 41,226 拍（923.52 → 824.52 µs，减少 10.72%）。
M1 为 9,612 → 9,606 拍，核内同为 8,923 拍且无预取。两条路径
共享 SRAM 读/写计数一致，M1 为 2,448/32，M125 为 4,432/4,000，
均来自 SoC 仿真。整板 16,287 LUT、11,238 FF、20 RAMB36、8 DSP，
WNS/WHS 为 +6.710/+0.069 ns。当时板上的易失位流为 `43494d47`。
[逐拍归因、复现命令及原始证据](INTERLAYER_SCHEDULE.md)

## 两层中间激活保留

2026-11-06，`upgrade/interlayer-cache` 从 `upgrade/two-layer-pointwise`
建立。源码 `a831757` 在第一层 SRAM 写提交时同步保存到独立双 bank。
同一 K7 50 MHz 位流完成 M1/M125 的两次 START、链式 SRAM 重读、两层
RV32IM C 和链式保留，中间及最终 INT8 逐字节匹配。M125 保留版比链式
重读少 881 拍端到端时间及 2,000 个共享读字，M1 端到端周期相同。
新增两块 RAMB36，候选 WNS/WHS 为 +7.173/+0.050 ns，当时板上的易失位流
为 `43494d46`。[层间保留合同、逐拍归因、复现与证据](INTERLAYER_CACHE.md)

## 两层一次提交

2026-11-06，从 `upgrade/banked-cache` 建立
`upgrade/two-layer-pointwise`。源码 `f842880` 完成链式一次 START、
CPU 两次 START 及两层 RV32IM C。三条路径共用中间 SRAM 地址
`0x80106000`。K7 50 MHz 布线通过，WNS/WHS 为 +7.019/+0.029 ns。
同一位流两次板测与 SoC 仿真逐项一致，M1/M125 的中间和最终 INT8
均逐字节匹配独立 golden。一次提交在 M1/M125 端到端分别省
164/152 拍。当时板上的易失位流为 `43494d45`。
[两层合同、计时边界、复现命令与实测证据](TWO_LAYER.md)

后续优化两层吞吐时，以本轮链式 SRAM 写回及重读为基线，量化
第二层首次输入填充在完整任务窗口内的成本，并保留两次 START 对照。

## 双 bank 回放

2026-11-06，`upgrade/banked-cache` 的 `de3c33e` 已通过双配置的
Questa 固定延迟扫参、可变等待真实激活和完整 SoC 固件仿真，也通过
Icarus 12.0 的固定一拍场景。SoC 仿真 M125 重叠从 26,719 降至
23,191 拍，宏等待输入从 12,420 降至 6,288 拍。两版 50 MHz 布线、实板
逐字节比较和热复位重提均通过。板测 M125 重叠少 3,528 拍，减少
13.20%。两版缓存各用两个 RAMB36。当时的 K7 默认构建为
`banked`，板上易失加载 `43494d44`。
复现命令、阶段归因、布线结果及精选日志见 [双 bank 对照](BANKED_REPLAY.md)。

## 四版共享 SRAM 对照

2026-11-06，`upgrade/sram-cache-matrix` 完成四种构建配置的固定延迟
扫参、可变等待真实激活回归、SoC 仿真、Vivado 20 ns 布线及同一 K7
的四版板测。K7 构建默认选择 combined。相对仅周转，M125 重叠从
29,323 到 26,719 拍，增加两个 RAMB36，M1 和 M125 阻塞周期持平。
当时板上加载易失候选 `43494d43`。软件基线、计数口径、原始记录和
真实命令见 [四版对照](SRAM_CACHE_MATRIX.md)。本轮比较无剩余硬件阻断。

若扩展到其他存储控制器，先复测该控制器的延迟和仲裁。保留
`--variant turnaround` 供一拍 SRAM 且 BRAM 紧张的系统使用。

## 请求周转候选归档

2026-11-06，`upgrade/sram-turnaround` 分支完成公开回归、固定/可变响应
波形基线和单未决读周转。新分支的两版 50 MHz 同板对照中，M125 重叠从
56,348 降至 29,324 拍，输出及热复位重提通过。Icarus 公开工作流已通过。
提交、原始结果位置和复现入口见 [共享 SRAM 请求周转](SRAM_TURNAROUND.md)。
当时加载的易失候选为 `43494d36`。

## v0.1.0 归档

原板测日期为 2026-11-05（Asia/Shanghai）。当前交付为 **K7 50 MHz v0.1.0**。
量化流水位流完成四项实板任务及两次运行中复位。干净目录重建了真实激活、
独立参考、算子 RTL、RV32I 固件、SoC 仿真和 Vivado 位流。新位流的 FPGA
配置载荷与原实测位流逐字节相同，原 routed DCP 的时序和资源也已复核。
现行结论、实际复现命令、产物清单及公开发布阻断统一见
[v0.1 发布说明](RELEASE_v0.1.md)。以下保留原始验收和历史对照。

## K7 量化写回流水化

热复位基线的最差 setup 路径从 `system/accel/recon_done_reg[0]/C`
到 `system/accel/output_bytes_reg[1][3]/D`，经过上下文及通道选择、
DSP 乘法、两次舍入和饱和，数据路径 18.836 ns（逻辑 10.813 ns，布线
8.023 ns）。在有符号 64 位乘积后插入一级使能寄存器，同时保存除法
指数、极值饱和标记、valid、上下文和通道编号。共享量化器仍每拍可发射
一个通道。通道 7 的结果实际进入输出缓冲后才开放写回，第二个字提交后
释放上下文，最终写提交和内部流水排空后置 DONE。复位清除待写结果的 valid。

同一 K7、50 MHz XDC、CPU、固件和 SRAM 镜像下，新布线的 WNS 为
+5.885 ns，WHS 为 +0.038 ns，内部未约束端点为 0，28,266 条可布线网
全部布通。量化前半段最慢路径为 9.785 ns，乘积到输出寄存器最慢为
12.327 ns。全设计最差路径移到 `system_run_reg/C` 至
`system/accel/macro_unit/weights_reg[39][10][3]/CE`，数据路径 13.819 ns，
其中布线 13.354 ns。整板资源为 15,826 LUT、10,956 FF、16 RAMB36、
8 DSP。DRC 为 0 错误、0 条 `REQP-1839`、20 条 DSP 建议。

两次板上热复位均记录 BUSY、旧读响应有效和 2 字已提交。复位后
STATUS、周期和提交计数均归零，SRAM 仅保留那 2 个已提交的结果字。
重新提交后每模式 M=1 提交 16 字、M=125 提交 2,000 字，逐字节匹配
同一真实激活的 golden。板测的复位快照与四项任务计数均与 SoC 仿真一致。

下表使用同一 `CIM_CYCLES` 窗口和 50 MHz（20 ns/拍）。窗口从 CiM START
到最终 SRAM 写提交和 DONE，CPU 装载、结果比较和 UART 输出在窗口之外。

|M|模式|热复位基线周期|流水版周期|基线用时 (µs)|流水版用时 (µs)|增量 (周期 / µs)|
|---|---|---:|---:|---:|---:|---:|
|1|阻塞、重叠各一项|4,756|4,764|95.12|95.28|8 / 0.16|
|125|阻塞|77,172|78,172|1,543.44|1,563.44|1,000 / 20.00|
|125|重叠|56,340|56,348|1,126.80|1,126.96|8 / 0.16|

同一新版的 M125 阻塞/重叠为 78,172 / 56,348 周期，延迟减少 27.9179%，
速度比 1.3873×。上表前后版本的增量来自量化结果多一拍，因果对照和波形见
[设计讲解](DESIGN_WALKTHROUGH.md)。

|归档当时执行的命令|结果与证据（`build/k7_qpipe/`）|
|---|---|
|`python tools/run.py --model`|复用来源已核验的真实激活，16 项完整 RTL 任务、64,512 字节比较 PASS；另覆盖量化结果 pending 时复位。见 `accel_simulation.log`、`accel_results.csv`、`accel_steady.csv`|
|`vlog -sv -work build/work rtl/cim_macro.sv rtl/requant.sv tb/tb_units.sv`、`vsim -c -lib build/work tb_units`（批处理 `run -all`）|Questa 2024.1 宏和量化单元 PASS，见 `unit_sim.log`|
|`python tools/k7.py prepare`、`python tools/k7.py sim`|同源镜像生成，RV32I SoC 两次热复位和四项重提 PASS，见 `build_metadata.json`、`soc_simulation.log`、`soc_results.json`、`soc_reset_results.json`|
|`python tools/k7.py impl`|K7 50 MHz 布线和 DRC PASS，见 `timing.rpt`、`check_timing.rpt`、`critical_paths.rpt`、`drc.rpt`；加载 `routed.dcp` 的分段报告为 `quant_product_paths.rpt`、`quant_writeback_paths.rpt`|
|`python tools/k7.py program --jtag <serial> --port <COM>`|JTAG DONE、`USR_ACCESS=43494d33` 和 UART `CIM_PASS`，见 `program_vivado.log`、`board_uart.log`、`board_results.json`、`board_comparison.json`、`verification.log`|

本版板测当时加载的易失位流为 `build/k7_qpipe/cim_k7.bit`，SHA256 为
`b2c18a796ce1559535d6723b9dbb4ac84b02f081a6ff34215457367bc6c67805`。
旧热复位位流原位保存在 `build/k7_reset/`，恢复方式见 [BOARD_K7.md](BOARD_K7.md)。

## 50 MHz 热复位基线

原布线报告将 `REQP-1839` 定位到 CPU 乘除单元的
`system/cpu/m_ext_inst/state_reg[1:0]`。状态逻辑进入 `dram_word_addr`
选择并驱动 RAMB36 的 `ADDRBWRADDR`。原 `myCPU_m_ext.sv:162`
在 `posedge rst` 异步更新状态。最小修复将生成副本的时序块改为
只在 `posedge clk` 采样，板级 SRAM 和 CPU 的运行门控也通过同步
寄存器采样。Vivado 日志确认读取 `build/k7_reset/cpu_include/` 中的
副本。原 CPU 源文件摘要与基线相同，修复前后的摘要在
`build/k7_reset/build_metadata.json`。

固件在任务 BUSY 且已有写提交后请求热复位。控制器等待下一条读请求
接受，在该读响应有效的时钟沿同步复位 CPU、CiM 和事务适配器。
复位事件记录与 SRAM 内容保留。UART 在两种模式下均记录
`STATUS_before=1`、复位沿读响应有效、复位前提交 2 字。重启后
STATUS、周期和提交计数均为 0，扫描整块 8000 字节输出只找到这 2 个
已提交的结果字，其余字均为预填标记。随后按同模式立即重新提交
M=125，再执行 M=1。每个新任务先用逐字取反的 golden 预填输出，
再核对结果及提交字数。

|M|阻塞板上周期|重叠板上周期|每模式已比较 INT8 字节|每模式写提交字数|
|---|---:|---:|---:|---:|
|1|4756|4756|64|16|
|125|77172|56340|8000|2000|

两次板上复位记录与 SoC 仿真一致。四项周期也与原 50 MHz 板测逐项
一致。仿真在复位沿断言存在未完成读，在下一拍检查旧响应、请求状态、
BUSY、DONE 和提交计数已清空。

新设计在 50 MHz 布线后的 WNS 为 +0.842 ns，WHS 为 +0.072 ns，内部
未约束端点为 0，27,593 条可布线网全部布通。DRC 中 `REQP-1839` 从
原报告列出的 20 条（规则报告上限）降至 0。新报告为 0 错误、22 条
DSP 流水建议。最差 setup 路径仍经过共享量化写回，数据路径 18.836 ns。
整板资源为 14,941 LUT、10,907 FF、16 RAMB36、8 DSP。

|基线当时执行的命令|结果与证据|
|---|---|
|`python tools/k7.py prepare`|编译 RV32I 固件、生成同步复位副本和同源数据，`build/k7_reset/build_metadata.json`|
|`python tools/k7.py sim`|两次复位、四项重提和逐字节比较 PASS，`build/k7_reset/soc_simulation.log`|
|`python tools/k7.py impl`|50 MHz 布线、setup/hold 通过且 `REQP-1839=0`，`build/k7_reset/timing.rpt`、`check_timing.rpt`、`drc.rpt`|
|`python tools/k7.py program --jtag <serial> --port <COM>`|JTAG DONE 和 `USR_ACCESS=43494d32`，两次复位和四项任务板测 PASS，`build/k7_reset/board_uart.log`、`board_results.json`|

当时板测使用的易失位流为 `build/k7_reset/cim_k7.bit`，SHA256
`6a75ca6f211d9b118e000fdd73c5545989c6699242226c4752d5350f15d81f98`。
原 50 MHz 位流及日志原位保留在 `build/k7/`，SHA256 校验与复位前 JTAG
回读均已记录。对照检查见 `build/k7_reset/verification.log` 和
`jtag_before.log`。复现与基线恢复见 [BOARD_K7.md](BOARD_K7.md)。

## 原始 50 MHz 基线

原理图确认 200 MHz 输入，教学工程 XPR/XDC 确认
`xc7k325tffg900-2` 与 20 ns CPU 时钟。JTAG 实际识别 `xc7k325t`，串口
使用 CP210x。教学 MiniRV 仍是学生模板，板级封装引用本机既有 JYDD
CPU、UART 和相关源文件，源路径和摘要记录于 `build/k7/build_metadata.json`。
板卡来源、内存映射、适配和复现步骤见 [BOARD_K7.md](BOARD_K7.md)。

初始核级综合定位到 W4A4 宏的 K64 逐项累加，20 ns 下估计 setup 裕量
−38.832 ns，路径 161 级逻辑。改用平衡归约树后，位平面顺序、累加位宽
合同、宏 latency/II 和外部接口保持一致。最终布线在 50 MHz 下
WNS=+1.275 ns、WHS=+0.073 ns、TNS/THS=0，26,830 条可布线网全部布通，
内部未约束端点为 0。最差 setup 路径经过共享量化并写回
`output_bytes`，数据路径 18.520 ns。异步 UART TX 是唯一输出时序例外。
DRC 为 0 errors、84 条报告告警，主要为 DSP 流水建议及既有 CPU 异步
控制到 BRAM。板测覆盖 JTAG 冷启动后的运行，失锁和运行中复位未实测。

|层次|LUT|FF|RAMB36|DSP|
|---|---:|---:|---:|---:|
|整板 `cim_k7_top`|14250|10933|16|8|
|加速器 `cim_accel`|9681|7925|0|4|
|其中 W4A4 宏|6636|4532|0|0|
|其中量化|662|0|0|4|

|M|阻塞板上周期|重叠板上周期|每模式已比较 INT8 字节|每模式写提交字数|
|---|---:|---:|---:|---:|
|1|4756|4756|64|16|
|125|77172|56340|8000|2000|

以上板上结果逐项与 RV32I SoC 仿真一致。M125 重叠模式周期减少 26.99%，
50 MHz 下任务窗口从 1.54344 ms 减至 1.12680 ms。窗口从 START 到最终
写回，含权重、参数和激活访问。CPU 预装、比较和串口输出另计。板级
SRAM 与下面独立算子回归的人工等待模型不同，两处周期分开记录。

|实际执行命令|结果及证据|
|---|---|
|`python tools/synth.py --part xc7k325tffg900-2 --period 20`|初始核级目标综合成功，原逐项累加 setup 违例，`build/synth/timing_synth.rpt`|
|`python tools/k7.py prepare`|xPack GCC 15.2.0 实际编译 RV32I/ILP32 固件，`build/k7/firmware_build.log`、`build_metadata.json`|
|`python tools/run.py --model`|平衡树后复用已核实真实激活，全 16 个算子任务、64,512 个输出 PASS，`build/simulation.log`|
|Questa `tb_units`|平衡树后宏极值和量化边界 PASS，`build/k7/balanced_units.log`|
|`python tools/k7.py sim`|Questa 2024.1 实际 CPU RTL 执行编译后固件，4 个任务 PASS，`build/k7/soc_simulation.log`、`soc_results.json`|
|`python tools/k7.py impl`|Vivado 2023.2 50 MHz 布线及时序检查 PASS，`build/k7/timing.rpt`、`check_timing.rpt`、`critical_paths.rpt`、`route.rpt`、`drc.rpt`、`utilization.rpt`|
|`python tools/k7.py program --jtag <serial> --port <COM>`|易失 JTAG 配置、DONE/USR_ACCESS 核对及真实板测 PASS，`build/k7/program_vivado.log`、`board_uart.log`、`board_results.json`|

板测位流为 `build/k7/cim_k7.bit`，SHA256
`fea3a602343992979349da096c7255ea88ce3ce378bc2617b9aade949ea1cdcf`，
JTAG 读回 USR_ACCESS=`43494d31`。首次配置成功后 Windows 控制台编码
打断串口采集，修复日志输出后以同一位流重跑并完整捕获 `CIM_PASS`。
原首次配置日志保留为 `build/k7/program_initial_console_encoding.log`。

## 已实现

- 初始目录只有 `codex_handoff/`，没有 `.git`、已有RTL/SoC、README或适用
  的根/上级AGENTS；已读取交接规格和来源，将项目约定合并至根 `AGENTS.md`。
  初始实现阶段未修改全局设置。
- `rtl/cim_accel.sv`：运行时MMIO锁存配置，tile外层/向量内层，32bit共享口
  加载权重、bias、multiplier、shift；一次START自主完成所有最终INT8写回。
  M=1..125，MODE0阻塞，MODE1两个输入槽/原生槽/输出上下文有限重叠。
- `rtl/cim_macro.sv`：实际W4A4低位计算、4096bit权重，A位平面3→0，偶列
  U4/奇列S4；原生结果224bit。主时钟latency4、最小II5，返回不可暂停。
- `rtl/requant.sv`：共享量化单元；锁定TF2.16.1 INT32双舍入；shift[-31,0]、
  multiplier非负，64bit乘积和宽位offset后饱和。原始输入翻转MSB，bias只加一次。
- 原生槽在发射前预约；低分片弹出后部分和继续保留；上下文在两个32bit
  写都提交后才释放；最终排空后sticky DONE。读最多一个未决、响应无ready；
  请求背压期间保持稳定。硬件及软件校验分界见 `docs/ARCHITECTURE.md`。
- `sw/cim.h/.c`、`sw/example.c`：寄存器、准备/可见性回调、打包、提交/轮询、
  超时及参数/地址/累加范围检查。通用示例由目标 BSP 传入映射；K7 已由
  `sw/k7_main.c` 和 `fpga/cim_rv_system.sv` 接入实际 RV32I SoC 并执行同一驱动。
- `fpga/synth.tcl`、`fpga/implement.tcl`：要求真实part/时钟或wrapper/XDC的
  入口；不提供猜测板卡默认值。`tools/synth.py --generic`可无器件执行。
- `tools/prepare_input.py`、`tools/export_activations.py`：固定来源MFCC整模型
  输入、TensorFlow2.16.1真实tensor23导出、来源/版本/字节对应记录，以及
  独立直接MAC+锁定量化与Interpreter tensor24的8000字节比较。
- `tools/run.py --real-activations`一条命令完成输入准备、导出、参考与RTL。
  原有合成输入保留，新增真实激活M125/1双模式任务。TB从M清单取尺寸。

## 实际命令与证据

本节为原阶段记录，干净目录复现见 [v0.1 发布说明](RELEASE_v0.1.md)。
原工作目录均为项目根，单元 xsim 命令除外。Windows 受限沙箱内编译器/EDA 曾
报DLL重定位、Access denied或xelab生成C编译失败；窄范围沙箱外运行后正常，
并非缺少已安装工具。Questa是全路径主仿真工具，不要求额外仿真器矩阵。

|命令|实际工具与结果|证据路径|
|---|---|---|
|`python tools/run.py --p1-only`|Questa 2024.1，阻塞M1/125最终INT8比较 PASS|`build/p1_simulation.log`、`build/p1_results.csv`|
|`python tools/run.py --real-activations`|首次端到端导出和 Questa 2024.1 回归，16 个连续完整任务 PASS；含真实激活 M125/1 双模式|导出证据见下行；当前 RTL 回归快照见 `build/k7_qpipe/accel_simulation.log`|
|上条入口内执行 `tools/export_activations.py`|TF2.16.1 BUILTIN_REF，实际导出tensor23；独立主机Golden与tensor24比较8000字节、0失配 PASS|`build/activation_export.log`、`build/activation_metadata.json`、`build/layer_activation.npy`|
|上条入口内执行 `tools/check_reference.py`|G++9.3.0，实际锁定TF/gemmlowp原函数与Python比较：3220次整数舍入、70次scale→参数 PASS|`build/reference.log`、`build/deps/official_quantization.inc`|
|上条入口内执行 `tools/export_model.py`|固定MLCommons模型解析/常量提取 PASS|`build/model_metadata.json`、`build/model_layer.json`|
|`python tools/synth.py --driver`|GCC9.3.0，严格C11编译例子/驱动，宿主打包/参数/范围校验 PASS|`build/checks/gcc_version.log`、`driver_compile.log`、`driver_test_compile.log`、`driver_test.log`|
|`python tools/synth.py`|Vivado2023.2 HDL analysis PASS；仅分析，不等于综合|`build/checks/syntax.log`|
|`python tools/synth.py --generic`|Yosys0.70，`synth -noabc`与`check -assert` PASS，0 problems|`build/checks/generic_synth.log`、`generic_stat.json`、`generic_netlist.json`|

本轮实际安装命令：`python -m venv build/tf_env`，随后
`build/tf_env/Scripts/python.exe -m pip install tensorflow==2.16.1`，成功安装
TensorFlow/TensorFlow-intel2.16.1及NumPy1.26.4。仅项目内隔离安装，系统
NumPy2.1.2和已有模型解析环境保持独立。完整安装输出在`build/tf_install.log`，
`pip freeze`在`build/tf_environment.txt`，可复现主依赖见`tools/requirements-runtime.txt`。
上轮12任务合成激活证据已保存在`build/archive/synthetic_activation_baseline/`，
包含原日志、CSV、case清单和模型元数据；当前标准日志对应本轮16任务。

流水化前单元测试使用 Vivado xsim 2023.2 并通过（1034 ns 仿真结束）。
当时在 `build/units/` 中执行的命令如下，见 `build/units/xsim.log`。

```
E:/Xilinx/Vivado/2023.2/bin/xvlog.bat -sv ../../rtl/cim_macro.sv ../../rtl/requant.sv ../../tb/tb_units.sv
E:/Xilinx/Vivado/2023.2/bin/xelab.bat tb_units -s units_sim
E:/Xilinx/Vivado/2023.2/bin/xsim.bat units_sim -runall
```

单元覆盖U14最高位为1（14400）、负S14（-7680）、位平面顺序、busy写拒绝、
valid一拍、II5连续启动、中途reset，以及高乘/负halfway/POT舍入/饱和。
负数舍入检查内部high/rounded，避免最终ReLU掩盖差异。

全路径使用独立直接整数MAC，随后调用经官方函数校验的量化；不复用DUT
四项分解。16个任务共比较64512个最终INT8字节，其中真实中间激活4个任务
比较16128字节。M长短交替，输入、权重与
参数均更换；MODE0/1使用相同数据与每任务复位的确定性存储等待模式。
检查首写96拍与最终写24拍有限阻塞、双活跃上下文、请求稳定、读响应一次、
无重复写、宏/存储服务次数、容量预约互斥、最终提交后DONE、DONE清除、
busy START拒绝但原任务完成、影子配置锁存、非法M/对齐/shift及复位后新任务。

## 周期、口服务与资源

下表取流水版 `build/k7_qpipe/accel_results.csv` 的定向等待 RTL 仿真数据。
周期含 8 次参数/权重装载、切换及排空。该测试中的装载、读响应和写接受等待
由测试平台注入，K7 周期以 UART 实测为准。

|M|阻塞MODE0|重叠MODE1|每任务最终输出|
|---|---:|---:|---:|
|1|8382|8382|64B|
|125|114290|91820|8000B|

该等待模型下，M125 重叠模式较阻塞模式少用 19.6605% 周期，周期比 1.24472。

每个M125任务实际2000次宏start，17216次32bit读、2000次32bit写，共19216次
存储服务：输入64000B、权重4096B、参数768B、输出8000B。实际口服务率为
0.168134/0.209279请求每主时钟拍（阻塞/重叠）。当前一次未决读和控制气泡
限制服务率，没有声称实现每拍一次请求。

权重驻留期间以各tile第一个到最后一个8B块第二写提交的间隔除以124，
平均块完成间隔为106.716734/83.998992拍（阻塞/重叠）。这项统计排除tile
装载和第一个块的启动延迟，保留当时合法存储等待；完整任务仍以上表为准。
原始各tile数据在 `build/k7_qpipe/accel_steady.csv`。M1不计算该区间平均。

平衡归约修改前的通用综合快照（无ABC、无FPGA映射）：宏84046 generic cells，量化9817，
外围本地22863（其中2个为层次实例）；全设计116726（含2个层次实例，
叶单元116724）。6条warning均为数组展开为寄存器，`check -assert`为0问题。
宏权重确实展开为4096个使能触发器，不能称为一个BRAM。两个MODE同网表；
未对裁剪成单上下文的网表做面积差实验，逻辑新增容量及控制成本分界见架构说明。
该快照记录技术无关的门级单元。当前 K7 实现资源和关键路径以上面的布线报告为准。

## 数据来源与 NOT_RUN

固定模型 `4addd0fa08d216e20637637874e084895f289da4`，53936B。重新解析op2的
tensor23/18/6→24，shape、INT8/INT32、RELU、stride/dilation/padding均核实。
真实weights范围[-127,127]、bias[-3308,4501]，真实scale生成shift为-8/-7。
当前同时验证“真实权重/参数 + 合成激活”和“真实权重/参数 + 实际模型中间激活”。
新输入是EEMBC仓库固定提交`cf7c2f2634608a7c0ea7458ab7cb3379f2863424`
的`tst_000000_Stop_7.bin`，来源说明为Speech Commands v2的49×10 INT8 MFCC，
490B；标签Stop/7。仅reshape为整模型`[1,49,10,1]`，未经重新量化。
整模型tensor0的zero-point=83，和本加速器目标层输入的-128不同，不混用。

TF2.16.1 reference resolver实际执行固定模型后，tensor23为`[1,25,5,64]`
INT8，共8000B、范围[-128,-32]、66个不同值，按NHWC空间行优先展开。
独立Golden与tensor24的8000个输出字节全部相同。RTL case6处理全部125行，
case7处理首行p=0；两者均覆盖阻塞和重叠。原case0..5保留原来源。
源URL/标签/变换/模型与字节摘要/运行时/导出方法见`docs/ACTIVATIONS.md`、
`build/inputs/input_metadata.json`及`build/activation_metadata.json`。
生成用例时核对模型、激活和来源记录，拒绝不匹配的旧导出。

此处只使用一个已发布MFCC样本，未从原始WAV重新提取、未恢复说话人/录音ID，
没有据此报告整网KWS准确率，也没有声称FPGA执行了前序层或整网。
固定源码、工具版本与许可见 `docs/THIRD_PARTY.md`、`docs/INTEGRATION.md`。

|步骤|状态与实际阻断|
|---|---|
|真实中间激活导出及RTL回归|PASS：已安装锁定runtime，从固定真实MFCC样本实际导出tensor23，完成主机8000字节交叉核对及M125/1双模式RTL最终写回比较|
|真实RISC-V程序执行/SoC集成|PASS：复用 JYDD CPU，实际编译并在 SoC 仿真和板上运行固件|
|目标FPGA综合、布局布线与板测|PASS：K7 V2.1，50 MHz setup/hold 通过，四个真实激活任务逐字节匹配|
|运行中热复位和重新提交|PASS：两种模式均在 BUSY 时中止 M=125，丢弃旧读响应并完成重新提交|
|MMCM 失锁时的 BRAM 行为|NOT_RUN：本轮实测使用 50 MHz 稳定时钟下的同步热复位|
|整网KWS准确率、模拟宏物理等价/能效|NOT_RUN：不属于当前单层RTL证据|

## 交付后续

50 MHz v0.1.0 发布范围为 Apache-2.0 许可的原创独立 IP 及板级接入代码。
整板复现需要取得有明确授权且匹配清单的 JYDD CPU/UART。对应整板位流、
生成的 CPU 副本及完整本地构建留在本地。见 [发布说明](RELEASE_v0.1.md)。

提频是后续可选项。可在独立目录优先检查 `system_run` 至宏权重写使能的扇出，
新频点通过时序和 DRC 后再按同一任务窗口验证用时。更高频点和 MMCM
失锁/重锁均为 NOT_RUN。

完整重跑主流程：

```
python tools/run.py --real-activations
```

首次模型解析依赖：`python -m pip install --target build/deps_python -r tools/requirements-model.txt`。
Python3.12.0；本机Questa/GCC/Vivado路径已自动发现，异机覆盖方式见README。
首次真实激活依赖：`python -m venv build/tf_env`，随后用该环境Python执行
`-m pip install -r tools/requirements-runtime.txt`。当前环境已装好，可直接运行
上面一条主命令。依赖与中间结果保存在build，源码不依赖未说明的预存最终答案。
