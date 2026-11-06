# 8 KiB 输入缓存双 bank 回放

从 `97bf98c` 的四版对照取 `combined` 作为参考。首先在真实固件的 SoC
仿真中采样每个任务时钟边沿，随后把 2,048×32 位缓存改成两个
1,024×32 位 bank。共享 SRAM 端口依旧是 32 位，最多一个未决读。
首 tile 按原响应的字索引奇偶分别写入 bank，后续 tile 每拍读取一对相邻
字。末对索引 14/15 写入上下文后才置输入就绪。两种构建共享宏、量化、
CPU、RV32IM 固件、激活、权重及 20 ns 时序约束。

## 逐拍归因

|M125 重叠，SoC RTL 仿真|32 位回放|双 bank 回放|
|---|---:|---:|
|完整任务周期|26,719|23,191|
|参数及权重阶段|4,163|4,163|
|宏启动与忙周期|10,000|10,000|
|宏未启动且有输入槽待填，完整任务|12,420|6,288|
|宏未启动且有输入槽待填，tile 1..7 运行阶段|10,542|4,410|
|本地回放端口占用|14,000|7,000|
|其他周期，完整任务|136|2,740|
|其他周期中两个上下文满且有量化或待写|0|2,170|
|共享 SRAM 读 / 写|3,216 / 2,000|3,216 / 2,000|

完整任务的互斥分类依次为参数/权重阶段、宏启动、宏忙、原生槽满、
已分配输入槽未填满、其他。两版归为原生槽满的等待均为 0。
回放、上下文、量化和写回事件与上述分类重叠。双 bank 减少 6,132 拍
输入等待，同时增加 2,604 拍其他时间。其中 2,170 拍可见两个上下文
均已占用且存在量化或待写结果。这个共现支持进一步检查上下文释放
时序。共享接口可见背压两版均为 3 拍，已接受读的额外响应等待为 0。

固定读响应 1/2/4/8 拍的独立 RTL 扫参中，M125 重叠均节省 3,528 拍。
这四点的外部延迟差异反映在公共参数/权重装载和首 tile 上。

下面取 M125 重叠任务的 tile 1，以该 tile 进入 RUN 的第一个采样沿
为第 0 拍。回放列记录 BRAM 发出读的边沿，数据在下一拍进入输入槽。

|事件|32 位回放|双 bank 回放|
|---|---:|---:|
|第 0 行回放读|2–17|2–9|
|第 0 行两次宏启动|19、24|11、16|
|第 1 行两次宏启动|36、41|21、26|
|第一组量化发射|31–38|23–30|
|第 0 行两个 SRAM 写提交|41、43|33、35|
|第 2 行首个回放读|46|38|

## K7 50 MHz 布线

|指标|32 位回放|双 bank 回放|
|---|---:|---:|
|整板 LUT / FF|16,858 / 11,044|16,227 / 11,047|
|加速器 LUT / FF|10,939 / 8,029|10,352 / 8,032|
|加速器本地控制及数据通路 LUT / FF|2,477 / 3,456|3,343 / 3,459|
|缓存 RAMB36 / 整板 RAMB36|2 / 18|2 / 18|
|整板 DSP|8|8|
|WNS / WHS (ns)|+6.919 / +0.067|+5.967 / +0.038|

两版均通过 Vivado 2023.2 布线，内部未约束端点、路由错误、DRC Error
及 `REQP-1839` 均为 0。各有 20 条 DSP 流水建议。双 bank 增加了
866 个本地 LUT 与 3 个 FF；整板 LUT 总数包含宏及量化器在本次综合的
映射差异。双 bank 版最长 setup 数据路径为运行控制到宏权重寄存器 CE，
耗时 13.739 ns，其中布线为 13.281 ns。32 位版最长数据路径是量化乘积
寄存器到写回字节寄存器，耗时 12.655 ns。

## 同板实测

2026-11-06 在同一 K7 V2.1 上先后易失加载 `43494d43` 和
`43494d44`。两版各完成四项真实激活任务，比较 16,128 个 INT8 字节，
并通过两次运行中热复位及重提。加速器周期和复位快照均与各自 SoC
仿真逐项一致。周期从接受 START 到最后写提交及 DONE，包含首次填充。

|任务|32 位回放，周期 / µs|双 bank 回放，周期 / µs|
|---|---:|---:|
|M1 两种模式各自|4,523 / 90.46|4,467 / 89.34|
|M125 阻塞|48,171 / 963.42|41,171 / 823.42|
|M125 重叠|26,719 / 534.38|23,191 / 463.82|

两版 RV32IM 软件结果一致，M1 为 23,013 拍，M125 为 2,749,533 拍。
选择 `banked` 作为本分支 K7 默认。M125 重叠少 3,528 拍（13.20%），
缓存容量与 BRAM 用量相同，且两版均满足 20 ns 约束。需要较低本地
逻辑开销或更多时序裕量时，保留 `--variant combined`。

## 验证与复现

Questa 2024.1 对每版运行 32 个固定延迟任务（1/2/4/8 拍、M1/8/32/125、
阻塞与重叠）及 22 个真实数据集可变等待任务。双 bank 检查每一对的对齐、
两个字均由当前任务填入、部分填充复位、最后一对待返回时复位和新任务
逐字节比较。固定一拍场景纳入 Icarus 工作流，并在 Ubuntu 24.04 的
Icarus 12.0 实跑通过，8 项周期和访问量逐项与 Questa 一致。

```bash
python3 tools/run.py --simulator iverilog --dataset matrix --memory fixed --variant banked
```

```powershell
foreach ($v in 'combined','banked') {
    python tools/run.py --simulator questa --dataset matrix --memory fixed --sweep-latency --variant $v
    python tools/run.py --simulator questa --dataset real --variant $v
    python tools/k7.py prepare --variant $v --out "build/k7_replay_$v" --cpu-source $cpuSrc --gcc-bin $rvBin
    python tools/k7.py sim --variant $v --out "build/k7_replay_$v" --cpu-source $cpuSrc --profile-tasks
    python tools/profile_replay.py "build/k7_replay_$v/task_edges.csv"
    python tools/k7.py impl --variant $v --out "build/k7_replay_$v" --cpu-source $cpuSrc
    python tools/k7.py program --variant $v --out "build/k7_replay_$v" --jtag $jtagSerial --port $serialPort
}
```

本轮实跑从四版对照已核验的 `build_metadata.json`、`firmware.mem`、
`sram.mem` 及 `cpu_include` 复制到 `build/k7_replay_<variant>_r2/`。
上面的 `prepare` 可重建这些输入。原始逐拍 `task_edges.csv` 保存在
各自的构建目录，精选仿真记录和固件摘要见
[证据目录](evidence/banked_replay_2026-11-06/)。
真实激活和 CPU/UART 外部依赖见 [板级流程](BOARD_K7.md)。
