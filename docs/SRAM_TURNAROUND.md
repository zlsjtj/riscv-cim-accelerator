# 共享 SRAM 请求周转 · 50 MHz

本分支从已发布的 `v0.1.0`（`cd84e03`）开始。保留旧位流、原报告和
Git 标签。用于归因的前后两版共享修复后的 START 计数及宏实现，使用同一
真实 tensor23、权重、逐通道参数、固件镜像、CPU 源及 50 MHz XDC。

|阶段|提交|范围|
|---|---|---|
|1|`3da2270`|确定性数据集、Icarus、标准单元测试、Actions、接受 START 后清计数|
|2|`b372682`|保留原调度，增加固定响应模型和逐拍证据，K7 USR_ACCESS `43494d35`|
|3|`72ab90b`|只对同一输入槽连续字回收读信用，K7 USR_ACCESS `43494d36`|

## 公开回归

Ubuntu 24.04 WSL 实际使用 Icarus 12.0 stable、Python 3.12.3、G++ 13.3.0。
旧 `tb_units` 在 Icarus 展开时报不支持非打包子程序端口。改用打包位平面参数，
量化内部 high、rounded 和最终字节的边界断言保留。旧过程式宏归约在 Icarus
中持续推进仿真时间，但多次重算整棵树，原回归在诊断时间窗内未完成。
按相同拓扑展开节点后，标准回归实际通过，宏的四位平面时序、原生位宽及
加法树均保持。第一阶段 Icarus 比较 3,220 组整数舍入、6 组 scale，运行
`tb_units`，随后 8 项完整算子共比较 32,256 个 INT8 字节。
第三阶段的 GitHub Ubuntu 24.04 runner 已通过同一标准入口
（[Actions 42063097810](https://github.com/zlsjtj/riscv-cim-accelerator/actions/runs/42063097810)，
测试提交 `72ab90b`），包括参考、单元及 14 项合成算子。

`--dataset synthetic` 是固定默认，`model` 使用真实权重和合成激活，
`real` 要求已有通过来源校验的 tensor23。`--real-activations` 先实际导出。
用存在模型缓存的目录实测 `--dataset synthetic --reference-only --skip-official-check`，
只生成合成用例，终端和 `reference.log` 都标记 SKIPPED。

板级写计数用核的 `start_accepted` 事件清零。SoC 定向测试在忙且已有提交时
写 START，核拒绝后继续原任务，最终 16 字均计入。空闲时 M=0 的 START
也保留计数，随后合法启动才清零。该用例与旧固件正常运行在独立仿真进程，
因此两版比较使用逐字节相同的固件。

## 固定响应波形和请求分类

`--memory fixed` 模拟始终 ready、读接受后下一拍返回。
`--memory variable` 保留原周期性请求背压、可变读响应及首/末写停顿。
`--trace-memory` 写出第一个阻塞 M=1 任务的逐拍 CSV。Icarus 同时输出 VCD。
表中拍数相对于各自 START；接受只计 `valid && ready` 的边沿。

|M=1 首 tile 事件|优化前|优化后|
|---|---:|---:|
|接收输入字 0 的请求|523|523|
|输入字 0 的响应|524|524|
|接收输入字 1 的请求|526|524|
|接收输入字 2 的请求|529|525|
|接收输入字 15 的请求|568|538|
|提交输出字 0|592|562|
|提交输出字 1|594|564|

8 个 tile 内的 120 次相邻输入读间隔全部从 3 拍变成 1 拍，8 次块内
连续写间隔均为 2 拍。原代码在第 524 拍消费响应，第 525 拍登记新读，
第 526 拍才接受。优化后第 524 拍同时消费旧响应和接受新地址。输出写
仍由原请求寄存器登记，写接受后经过一拍再登记下一写。

|真实 M125 重叠，RTL 仿真|周期前→后|端口背压拍前→后|读已接受且还未返回前→后|其余无传输拍前→后|
|---|---:|---:|---:|---:|
|一拍响应、始终 ready|56,344 → 29,320|0 → 0|0 → 0|37,128 → 10,104|
|可变等待|91,820 → 78,938|5,490 → 5,197|29,651 → 45,413|37,463 → 9,112|

分类互斥。端口背压为请求有效且未接受，响应等待为已接受的读在该拍未返回。
其余无传输还包含宏执行、量化、换 tile 等。因此调度控制空拍由相邻读的
逐拍轨迹单独判断。可变模型按接受时刻生成等待长度，改变发射时间会改变
抽到的等待序列。响应等待计数上升与外部延迟分布和同拍重叠有关，不能当作
接口响应被 RTL 拉长。两模型均完成相同的 19,216 个外部事务。

## 优化合同与覆盖

只在输入字 0..14 返回时发出同一上下文的下一字，参数、权重、块边界和
输出写的调度保持原语义。已就绪写回优先。旧数据使用旧 `rd_ctx/rd_index`
落到已分配输入槽；新接受边沿更新索引和下一地址。pending 在旧响应消费后
按该拍是否接受新读更新。若下游在响应拍不接收新读，把同一地址和标签
转入原请求寄存器并保持至接受，旧响应仍正常消费。

候选 Questa 2024.1 在真实数据集、两种响应模型下分别通过 22 项完整
算子，各比较 81,024 个字节。合成边界用例覆盖 M=1/2/3/124/125，真实 tensor23
覆盖 M1/125。
检查同拍信用与新旧标签、拒绝越过 word 15、延迟及背压稳定、参数错误排空、
权重提交、最后一字提交才释放上下文、最终 DONE 排空、读和量化在途复位。
另在 word 14 返回且已提出 word 15 请求时复位，重启后完整回归通过。

## 同频布局布线

两版均使用 Vivado 2023.2、`xc7k325tffg900-2` 与同一 XDC。同步 M 单元
副本、`firmware.mem` 和 `sram.mem` 的 SHA-256 逐项一致。

|物理指标|匹配基线|请求周转|差值|
|---|---:|---:|---:|
|整板 LUT|14,770|16,115|+1,345|
|整板 FF|10,955|11,005|+50|
|整板 RAMB36 / DSP|16 / 8|16 / 8|0 / 0|
|加速器 LUT / FF|9,649 / 7,973|10,915 / 8,023|+1,266 / +50|
|加速器本地行 `(accel)` LUT / FF|2,453 / 3,400|2,451 / 3,450|−2 / +50|
|宏层级 LUT|6,378|7,709|+1,331|
|量化层级 LUT|821|756|−65|
|WNS / WHS (ns)|+6.838 / +0.089|+7.022 / +0.075|+0.184 / −0.014|

整板 LUT 上升是本次实测物理成本。两版宏和量化器源相同，但综合与实现后
层级映射不同。层级 LUT 合并导致本地行和从父层减子层所得计数略有差异。
本地行实测 −2 LUT、+50 FF，整板 LUT 差不能视为请求控制独占面积。
两版内部未约束端点、时序失败
端点和 DRC 错误均为 0，分别布通 27,187 / 28,325 条网，保留 20 条 DSP
流水建议。最差 setup 由宏位平面到结果寄存器的 12.917 ns 路径移到
量化乘积到输出字节寄存器的 12.797 ns 路径。两版均满足 50 MHz。
原始证据为各自 `build/k7_sram_*/` 下的 `utilization.rpt`、`timing.rpt`、
`check_timing.rpt`、`critical_paths.rpt`、`route.rpt` 和 `drc.rpt`。
重开候选 routed DCP 后测得，适配器 `mem_rvalid_reg` 到共享 BRAM 最差 setup
路径为 7.115 ns，slack +12.210 ns，见 `return_to_sram.rpt`。

## K7 实板结果

2026-11-06 在同一 K7 依次加载匹配基线 `43494d35` 与候选 `43494d36`。
周期窗口从 CiM START 到最终 SRAM 写提交及 DONE，包含全部 tile 装载和排空，
CPU 预装、比较和 UART 在窗口外。时间按 50 MHz（20 ns）换算。

|M|模式|基线周期 / µs|优化周期 / µs|时间减少|
|---|---|---:|---:|---:|
|1|阻塞、重叠各一项|4,764 / 95.28|4,524 / 90.48|5.04%|
|125|阻塞|78,172 / 1,563.44|48,172 / 963.44|38.38%|
|125|重叠|56,348 / 1,126.96|29,324 / 586.48|47.96%|

两版各核对四项任务 16,128 个 INT8 字节，0 失配，各通过两次运行中热复位
和重提。K7 周期和复位快照分别与各自的 SoC 仿真逐项一致。匹配基线周期
也与 v0.1.0 原板测相同。M1 的 240 拍和 M125 阻塞的 30,000 拍收益，
与 8 个 tile 中每个输入块少等 15×2 拍相符。重叠原已隐藏部分开销，因此
M125 重叠的实际收益为 27,024 拍。固定一拍独立模型的各项完成周期比板上
少 4 拍，保留为不同证据口径。

本地原始记录在基线 `build/sram-ii-baseline/build/k7_sram_baseline/`
和候选 checkout 的 `build/k7_sram_ii1/`，包含 `board_uart.log`、
`board_results.json`、`soc_results.json` 和 `start_counter.log`。
候选目录另有 `board_comparison.csv` 与 `verification.log`。
两版位流校验摘要分别为
`05ff5ea529f19f735c4c520d13ce3dce40b678c31f3e2a7139b33df6a1efc568`
和 `9e9bc3207e45867a94e70dd55b3a13d7dccbf33b11d63039457dddb26fcb8bb8`。

## 剩余瓶颈

M125 仍需读取 16,000 个输入字、1,216 个权重/参数字并提交 2,000 个输出字。
固定响应重叠的 29,320 拍中有 19,216 拍发生共享口传输，约占 65.5%。
输入槽切换、参数/权重装载及两拍写入间隔仍留下控制开销。8 KiB 输入缓存
可减少重复搬运，仍作为独立后续候选，本分支没有加入它。

## 复现

```powershell
python tools/run.py --dataset synthetic --simulator iverilog
python tools/run.py --dataset real --simulator questa --memory fixed --trace-memory
python tools/run.py --dataset real --simulator questa --memory variable
python tools/k7.py prepare --cpu-source $cpuSrc --gcc-bin $rvBin
python tools/k7.py sim --cpu-source $cpuSrc --trace-blocks
python tools/k7.py impl --cpu-source $cpuSrc
python tools/k7.py program --jtag $jtagSerial --port $serialPort
```

分别检出 `b372682` 和 `72ab90b` 到独立目录。真实激活首次按 README
用 `--real-activations` 生成。整板需获授权的 JYDD CPU/UART。
固定/可变原始周期分别在 `build/fixed_results.csv`、`build/results.csv`，
分类计数在 `fixed_profile.csv`、`variable_profile.csv`，轨迹在
`fixed_trace.csv`，Icarus 波形为 `fixed_memory.vcd`。
