# 第二层量化与写回重叠

从 `upgrade/interlayer-replay-schedule` 的 `4665433` 建立
`upgrade/interlayer-writeback-schedule`。RTL 与测量入口提交为
`777c941`。比较项是提前回放（方法 4）和提前写回（方法 5）。
两条路径使用同一宏、输入、两层 golden、SRAM 地址和计时固件。
第一层使用真实 tensor23 激活，第二层使用固定种子权重和量化参数，
两级 golden 均由独立整数参考生成。

## 首个 tile 的 389 拍

用带上下文标签的 Questa 2024.1 SoC 仿真重跑上一版固件。M125 第二层
首 tile 的 1,649 个 RUN 拍与本轮固件的提前回放路径逐拍一致，
其中宏启动和忙 1,250 拍、输入等待 10 拍、原生槽满 0 拍、其余
389 拍。其余周期内，两个、一个、零个活跃上下文分别占 249、138、
2 拍。

下表每个其余周期只归入一类。分配事件优先，否则按最早在途行的
状态和当拍握手归类。量化及写提交可以并行，互斥分类之外另计实际
事件。例如基线这 389 拍内，量化发出 195 次、返回 134 次。

|M125 第二层首 tile 的其余周期|提前回放|提前写回|
|---|---:|---:|
|生成写请求|126|64|
|低字提交|63|1|
|高字提交|63|2|
|上下文分配|124|124|
|量化发出／普通返回／末路返回|1 / 7 / 2|1 / 5 / 2|
|等待宏返回／重建／tile 退出|1 / 1 / 1|0 / 1 / 1|
|共享 SRAM 背压|0|0|
|合计|389|201|

两版的低字、高字各实际提交 125 次。优化版的 122 次末字提交与
上下文分配同拍，归入上表的分配项。首个 tile 有 186 拍两个上下文
都占用。宏和输入等待周期均未变。

以首个 tile 的 RUN 首拍为 0，第一行通道 3 和 7 的量化结果分别在
第 27 和 31 拍返回。旧版等通道 7 返回后才登记低字请求，第 33 拍
提交低字，第 35 拍提交高字，第 36 拍分配预取行，第 37 拍发宏。
新版在第 29 拍提交低字，第 33 拍提交高字并接续预取行，第 34 拍
发宏。后续每两行的宏启动组间隔由 26 降到 23 拍。末宏忙拍后至
tile 退出由 16 降到 14 拍，末路量化到末字提交的间隔由 4 降到
2 拍。

## 控制合同

`banked-early-write` 在原 `0x1d` 上增加 CONTROL bit 5
（`CIM_EARLY_WRITE`，写入 `0x3d`）。它要求 MODE1、链式保留和
提前回放，实际调度变更只在第二层启用。

- 通道 3 的结果入寄存器后，低 32 位即可通过原请求寄存器发出。
  高 32 位等通道 7 返回，且低字已实际提交。
- 末字提交通过原 SRAM 握手确认。若该拍正好提交预取槽旧行的高字，
  且预取 BRAM 已无未完成读，控制器可以同拍安装新行。提交使用旧
  请求的地址和数据，新行最早下一拍发宏。
- 定向仿真分别停住低字和末字，在低字恢复提交后继续阻塞末字，
  检查地址和上下文归属并在阻塞中复位。完整 SoC 回归检查两级
  golden、最终读、真实提交计数和同拍接续。M125 共 1,000 次提前
  低字提交和 976 次同拍接续。22 项单层真实数据回归也通过。

## SoC 仿真与流量

|任务|提前回放核内周期|提前写回核内周期|共享 SRAM 读 / 写|本地缓存读 / 写|
|---|---:|---:|---:|---:|
|M1|8,923|8,907|2,448 / 32|240 / 16|
|M125|40,543|39,039|4,432 / 4,000|30,000 / 2,000|

流量是两种调度共有的 SoC 握手计数，以 32 位字为单位。两版第二层
的中间 SRAM 重读均为 0。端到端从输入就绪后启动计时，到 CPU 读取
最终输出最后一字后提交停表，比较 golden 与 UART 输出在窗口外。
同一固件下，仿真端到端 M1 为 9,611 → 9,606 拍，M125 为
41,231 → 39,730 拍。两条路径共享调用点，但驱动校验与 CPU 轮询
也在该窗口内。核内周期可单独归因到 RTL。

## K7 50 MHz 布线

两次均为 `xc7k325tffg900-2`、20 ns 时钟约束下的整板布线报告。
本轮同位流 `43494d48` 同时包含两种可选调度。下表用上一轮独立
布线的 `43494d47` 作资源和时序对照，差值也包含固件与综合映射差异。

|指标|归档提前回放 `43494d47`|本轮 `43494d48`|
|---|---:|---:|
|整板 LUT / FF|16,287 / 11,238|16,376 / 11,233|
|加速器 LUT / FF|10,485 / 8,223|10,450 / 8,218|
|外围控制本级 LUT / FF|3,307 / 3,650|3,313 / 3,645|
|宏代理 LUT / FF|6,415 / 4,532|6,320 / 4,532|
|量化模块 LUT / FF|767 / 41|820 / 41|
|整板 RAMB36 / DSP|20 / 8|20 / 8|
|输入缓存 / 层间缓存 RAMB36|2 / 2|2 / 2|
|WNS / WHS (ns)|+6.710 / +0.069|+6.071 / +0.085|

布线错误、内部未约束端点、DRC Error 和 `REQP-1839` 均为 0。
本轮 20 个 DRC 告警为既有 DSP 流水建议。最长 setup 路径由量化
乘积 DSP 寄存器到输出字节寄存器，数据延迟 13.686 ns，其中逻辑
6.498 ns，布线 7.188 ns。原报告和 routed DCP 保存在
`build/k7_interlayer_writeback/`。

## K7 50 MHz 实测

2026-11-06，在同一块 K7 加载并读回 `43494d48`。M1 和 M125 各
运行六条路径，两层各检查 64 和 8,000 字节。12 次任务共比较
96,768 字节，零失配，UART 返回 `CIM_PASS`。12 个端到端周期
均与本轮 SoC 仿真一致。

|任务|提前回放|提前写回|节省|
|---|---:|---:|---:|
|M1|9,611 拍 / 192.22 µs|9,606 拍 / 192.12 µs|5 拍 / 0.10 µs|
|M125|41,231 拍 / 824.62 µs|39,730 拍 / 794.60 µs|1,501 拍 / 30.02 µs（3.64%）|

归档位流的提前回放为 9,606／41,226 拍，本轮对照使用新位流中
重跑的 9,611／41,231 拍。核内的提前回放结果与归档完全相同。
M1 的核内收益为每 tile 2 拍，共 16 拍，完整窗口包含 CPU 开销，
实际少 5 拍。

[原始 UART](evidence/interlayer_writeback_2026-11-06/board_uart.txt)、
[板测与仿真对照](evidence/interlayer_writeback_2026-11-06/comparison.csv)、
[逐拍节选](evidence/interlayer_writeback_2026-11-06/tile0_classified_edges.csv)、
[逐拍分类计数](evidence/interlayer_writeback_2026-11-06/backend_counts.csv)、
[流量](evidence/interlayer_writeback_2026-11-06/traffic.csv)、
[布线报告摘录](evidence/interlayer_writeback_2026-11-06/routed.json)及
[工具与输入哈希](evidence/interlayer_writeback_2026-11-06/common.json)。

## 复现

使用 [K7 本地依赖与真实激活](BOARD_K7.md)。本轮使用 Questa
2024.1、Vivado 2023.2 和 xPack RV32IM GCC 15.2.0。两层 fixture、
SRAM 镜像与 JYDD 源文件哈希均与归档提前回放版一致。

```powershell
python tools/run.py --simulator questa --dataset real --variant banked-early-write
python tools/k7.py prepare --two-layer --variant banked-early-write --cpu-source $cpuSrc --gcc-bin $rvBin
python tools/k7.py sim --two-layer --variant banked-early-write --profile-tasks --cpu-source $cpuSrc
python tools/profile_replay.py build/k7_interlayer_writeback/task_edges.csv --backend-tile0 11
python tools/profile_replay.py build/k7_interlayer_writeback/task_edges.csv --backend-tile0 12
python tools/k7.py impl --two-layer --variant banked-early-write --cpu-source $cpuSrc
python tools/k7.py program --two-layer --variant banked-early-write --jtag $jtagSerial --port $serialPort
```

上面任务 11、12 分别是 M125 方法 4、5。要在独立目录复跑历史基线，
在相同源码与依赖下使用 `--variant banked-prefetch --out $baselineOut`
执行 `prepare` 和带 `--profile-tasks` 的 `sim`，选择任务 10。
本轮重跑复用了历史基线原始 `firmware.mem`、`sram.mem`、
`cpu_include` 与构建元数据，并通过脚本的哈希检查。
