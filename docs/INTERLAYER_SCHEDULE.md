# 第二层提前回放

从 `upgrade/interlayer-cache` 的 `318dcbe` 建立对照。第一层按原
写提交保存中间结果到 SRAM 和两个片上 bank。第二层在这些 bank
回放，继续使用原有两个输入槽和两个输出上下文。

## 首个 tile 的逐拍归因

原片上保留版 M125 的第二层首 tile 从 RUN 首拍到切换共 2,269 拍。
宏启动和忙共 1,250 拍，输入等待 630 拍，其余 389 拍，原生结果
容量等待为零。输入等待指宏既未启动也不忙、原生槽有容量且存在
输入未齐的已分配上下文。630 拍包括发出本地 BRAM 读的 504 拍和
未发读的 126 拍。基线反复在两行一组的边界等待旧上下文写回释放，
之后才为下一行排队并填满输入槽。其余 389 拍中，310 拍两个上下文
均占用。最后一个宏忙拍之后至 tile 切换有 16 拍，包含量化、输出写
提交及排空确认。

最后一个高位分片的位平面被宏采样后，该行的输入向量已可覆盖。
启用提前回放时，若两个上下文仍占用、当前输入都齐且本地回放空闲，
调度器把下一行的八个字对写入已经消费完的输入槽。旧上下文保留
自己的位置、量化和写回状态。只有旧行最后一字提交且新行回放
排空后，新行才进入可发宏的状态。一次最多预约一行，预约期间
`next_p` 保持稳定。

以 M125 第二层首 tile 的 RUN 首拍为 0，旧行的最后一个高位
位平面在第 20 拍采样，最后一字在第 35 拍提交。基线在第 38–45 拍
回放下一行，到第 47 拍才发宏。提前回放把取数移到第 22–29 拍，
下一行在第 37 拍发宏。此后每两行的宏启动组间隔从 36 降到 26 拍。

`banked-prefetch` 在原链式保留的 CONTROL 值 `0x0d` 上增加
`CIM_PREFETCH`，写入 `0x1d`。提前回放只在第二层片上回放的
重叠模式生效，覆盖该层所有 tile。基线和优化路径可在同一位流
运行，并使用同一个计时内驱动调用点。

## SoC 仿真

|M125 第二层首 tile|片上保留基线|提前回放|
|---|---:|---:|
|RUN 周期|2,269|1,649|
|宏启动和忙|1,250|1,250|
|输入等待|630|10|
|其中发本地读 / 未发本地读|504 / 126|8 / 2|
|其他周期 / 其中两个上下文满|389 / 310|389 / 249|
|末次量化返回相对 RUN 首拍|2,263|1,643|
|末次 SRAM 写提交相对 RUN 首拍|2,267|1,647|
|最后宏忙拍后的排空|16|16|

M125 第二层每个 tile 的 RUN 节省 620 拍。完整核窗口从
45,503 降到 40,543 拍，共少 4,960 拍。提前回放共预约 984 行，
即每个 tile 启动后为后续 123 行提前取数。两条路径的共享 SRAM
读/写计数均为 4,432/4,000 个 32 位字，第二层中间 SRAM 读均为 0。
M1 两条路径均为 2,448/32 次共享读/写。

定向仿真覆盖预取数据返回后、旧输出仍因 SRAM 背压而不能提交。
检查旧行位置和下一行预约不变，并在该状态复位。连续任务检查
宏仍在采样的槽不会被预取覆盖，复用时旧写提交和新回放都已排空。
原单层真实数据集回归通过 22 项任务。

## K7 50 MHz 布线

原保留版采用归档位流的布线报告。本轮的基线与提前回放板测共用
`43494d47` 的网表和固件。

|指标|归档保留位流 `43494d46`|本轮位流 `43494d47`|
|---|---:|---:|
|整板 LUT / FF|16,248 / 11,236|16,287 / 11,238|
|加速器 LUT / FF|10,470 / 8,221|10,485 / 8,223|
|整板 RAMB36 / DSP|20 / 8|20 / 8|
|输入 / 层间缓存 RAMB36|2 / 2|2 / 2|
|WNS / WHS (ns)|+7.173 / +0.050|+6.710 / +0.069|

本轮在 `xc7k325tffg900-2` 上通过 20 ns 约束，内部未约束端点、
路由错误、DRC Error 和 `REQP-1839` 均为 0。最长 setup 数据路径
从 `system_run_reg` 到宏权重寄存器的 CE，耗时 12.831 ns。
整板资源差值含两次综合映射和固件 ROM 的差异。

## K7 50 MHz 板测

2026-11-06 在同一位流 `43494d47` 中运行五条路径。每个配置分别
对照独立 golden 检查第一层中间输出和第二层最终输出，两层各检查
M1 的 64 字节和 M125 的 8,000 字节。十次任务共检查 80,640 字节，
零失配，UART 返回 `CIM_PASS`。

|执行路径|M1 周期 / µs|M125 周期 / µs|
|---|---:|---:|
|CPU 两次 START|9,767 / 195.34|47,200 / 944.00|
|链式 SRAM 重读|9,612 / 192.24|47,057 / 941.14|
|两层 RV32IM C|46,009 / 920.18|5,493,596 / 109,871.92|
|链式片上保留|9,612 / 192.24|46,176 / 923.52|
|链式提前回放|9,606 / 192.12|41,226 / 824.52|

M125 相对片上保留减少 4,950 拍（99.00 µs，10.72%）。端到端窗口
含 CPU 配置、轮询和最终读，因而与核内的 4,960 拍节省相差 10 拍。
M1 两条路径核内均为 8,923 拍，预取次数均为 0。其端到端相差
6 拍，逐拍证据未将该差值归因到具体的 CPU 或总线事件。硬件路径的
端到端板测周期均与 SoC 仿真一致。共享 SRAM 计数来自 SoC 握手记录。

[原始 UART](evidence/interlayer_schedule_2026-11-06/board_uart.txt)、
[板测与仿真对照](evidence/interlayer_schedule_2026-11-06/comparison.csv)、
[流量](evidence/interlayer_schedule_2026-11-06/traffic.csv)、
[逐拍节选](evidence/interlayer_schedule_2026-11-06/tile0_early_edges.csv)、
[布线摘录](evidence/interlayer_schedule_2026-11-06/routed.json)和
[工具与输入哈希](evidence/interlayer_schedule_2026-11-06/common.json)。
完整本地报告 `timing.rpt`、`utilization.rpt`、`check_timing.rpt`、
`route.rpt`、`drc.rpt` 和逐拍 `task_edges.csv` 保存在
`build/k7_interlayer_schedule/`。

## 复现

使用 [K7 板级工具和真实激活](BOARD_K7.md)。先复算原基线，再构建
同一位流的两条路径。

```powershell
python tools/profile_replay.py --second-tile0 build/k7_interlayer_final/task_edges.csv
python tools/run.py --simulator questa --dataset real --variant banked-prefetch
python tools/k7.py prepare --two-layer --variant banked-prefetch --cpu-source $cpuSrc --gcc-bin $rvBin
python tools/k7.py sim --two-layer --variant banked-prefetch --profile-tasks --cpu-source $cpuSrc
python tools/profile_replay.py --second-tile0 build/k7_interlayer_schedule/task_edges.csv
python tools/k7.py impl --two-layer --variant banked-prefetch --cpu-source $cpuSrc
python tools/k7.py program --two-layer --variant banked-prefetch --jtag $jtagSerial --port $serialPort
```

UART `CHAIN_RESULT` 路径编号 3 是片上保留，4 是提前回放。两条
路径保留同一中间 SRAM 地址 `0x80106000`，最终输出地址
`0x80108000`。计时窗口从输入就绪到 CPU 读过最终结果后的停表提交。
