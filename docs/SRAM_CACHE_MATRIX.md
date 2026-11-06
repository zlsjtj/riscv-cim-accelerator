# 共享 SRAM 请求周转与输入缓存

本文的默认配置决策对应四版对照提交 `97bf98c`。
后续 K7 默认选择见 [双 bank 回放](BANKED_REPLAY.md)。

四版从公开请求周转分支 `76194e4` 派生，共用 `0adaca2` 的宏、量化器、
SoC、RV32IM 固件、tensor23 和 50 MHz XDC。旧版
[`v0.1.0`](RELEASE_v0.1.md) 及 [请求周转原始对照](SRAM_TURNAROUND.md)
保留各自的计时与构建条件。原先单独完成的 scratchpad、软件算子、计时器、
原板测与构建说明保存在 [归档提交 4736042](https://github.com/zlsjtj/riscv-cim-accelerator/tree/473604209cbe7046e97dce9477e9452ab14b8901)。

|构建配置|TURNAROUND|INPUT_CACHE|USR_ACCESS|
|---|---:|---:|---|
|baseline|0|0|`43494d40`|
|turnaround|1|0|`43494d41`|
|cache|0|1|`43494d42`|
|combined|1|1|`43494d43`|

同一个源文件用 elaboration 参数改变控制和存储。TURNAROUND 在输入字
0..14 返回时提出同一上下文的下一个字，沿用一个共享未决读信用。已准备好
的写回优先。若端口不能接受，现有请求寄存器接住地址与标签。旧响应仍按旧
索引进入输入槽。关闭该选项时，地址前推寄存器和响应到请求的旁路被常量折叠。

INPUT_CACHE 在 tile 0 的共享读响应拍保存原始 32 位输入字，并同时送入原
输入槽。位置索引乘 16 加字索引构成地址，125×16 个字需要 8,000 B，
物理深度取 2,048×32 位。tile 1..7 从单端口同步 BRAM 回放，每次 16 字，
上下文标签随数据延迟一拍。填充和重放分属不同 tile。每次合法 START 从
tile 0 重新填充，复位撤销未决标签，BRAM 数据无需清零。后续任务只使用
该任务重填的地址范围。DONE 等待最后一个 SRAM 写提交和内部状态排空。
关闭缓存时综合移除缓存 RAM、回放读地址和标签状态。

### 访问量和计时口径

每个任务都有 1,216 个权重及参数读、16M 个共享输出写。其余为输入。

|M|缓存|共享读接受|共享写提交|本地读|本地写|
|---|---|---:|---:|---:|---:|
|1|关|1,344|16|0|0|
|1|开|1,232|16|112|16|
|125|关|17,216|2,000|0|0|
|125|开|3,216|2,000|14,000|2,000|

访问计数取自实际 SoC RTL 握手与缓存端口，板上 UART 另核对已提交写数。
带缓存时 M125 的共享读减少 14,000 次（81.32%），共享总事务减少
72.86%。加速器从接受 START 到最终共享 SRAM 写提交及 DONE，包含整个
首次填充。软件从 MMIO 计时启动到停止，包含 RV32IM C 调用、八个并行
标量累加量的 tile 内循环、双舍入和 SRAM 输出写回。SoC 仿真中软件停表
在最终写后 26 拍（M1）或 29 拍（M125）。两种窗口均排除 CPU 预装、
golden 逐字节比较和 UART。软件使用同一 CPU、同一数据布局及 C 标量
算子，编译目标为 RV32IM。

### 独立 RTL 固定响应

Questa 2024.1 每版运行 32 项任务，固定响应延迟分别为 1、2、4、8 拍，
无额外背压。每个点覆盖 M1/8/32/125 和两种调度。下表列出重叠调度
的 M125 任务周期，均为独立 RTL 仿真结果。

|固定响应|baseline|turnaround|cache|combined|combined 相对 turnaround 少用周期|
|---:|---:|---:|---:|---:|---:|
|1 拍|56,344|29,320|30,094|26,716|2,604|
|2 拍|77,032|45,544|33,744|29,808|15,736|
|4 拍|111,064|79,976|40,126|36,240|43,736|
|8 拍|176,856|148,840|52,606|49,104|99,736|

一拍响应下，组合相对仅周转在 M1 两个模式及全部阻塞任务周期相同。
在重叠模式，M8、M32、M125 分别节省 133、637、2,604 拍
（2.27%、5.97%、8.88%）。周转后的共享读已能在每拍返回并接受下一字。
阻塞调度仍要等输入槽填满，局部回放同样每拍一字。重叠时，回放与共享
写使用不同端口，减少输入和输出相互争用。

在固定响应至少 2 拍的本模型中，组合在全部测试规模及模式上都比仅周转快。
M1 在 2 拍时已节省 112 拍（1.91%）；M125 重叠在 2/4/8 拍时分别
节省 34.55%/54.69%/67.01%。这组结果适用于单未决共享读、固定响应和
始终 ready；实际仲裁与延迟分布会改变精确百分比。

四版另各跑 22 项可变等待的真实数据集回归。每版比对 81,024 个 INT8
字节，包含真实 tensor23 和合成边界向量。固定扫参与可变等待复用同一
记分板，覆盖连续任务更换输入及 M、读/量化在途复位、最后字和最后写
背压。缓存版另在 tile 0 索引 5 的字返回时复位，再用内容不同的输入启动。
记分板逐地址确认每个缓存重放字已经由当前任务写入。公开 Icarus 12.0
的可变等待周转、固定一拍组合两个作业均通过官方参考、单元及算子检查。
[Actions 42069221643](https://github.com/zlsjtj/riscv-cim-accelerator/actions/runs/42069221643)

### K7 50 MHz 布线

|构建|整板 LUT / FF|加速器 LUT / FF|加速器本地控制及数据通路 LUT / FF|整板 RAMB36 / DSP|WNS / WHS (ns)|
|---|---:|---:|---:|---:|---:|
|baseline|16,743 / 11,002|10,889 / 7,987|2,366 / 3,414|16 / 8|+6.565 / +0.071|
|turnaround|16,922 / 11,034|11,102 / 8,019|2,583 / 3,446|16 / 8|+6.752 / +0.076|
|cache|16,811 / 11,014|10,993 / 7,999|2,471 / 3,426|18 / 8|+6.329 / +0.070|
|combined|16,858 / 11,044|10,939 / 8,029|2,477 / 3,456|18 / 8|+6.919 / +0.067|

四版均有 0 个内部未约束端点、0 个路由错误、0 条 DRC Error、
0 条 `REQP-1839`，各有 20 条 DSP 流水建议。两版缓存均恰好推断两个
RAMB36E1。两版周转均保留 32 个前推地址触发器，关闭后为零。
整板 LUT 受宏、量化和 CPU 层次映射影响。组合相对仅周转整板
减少 64 LUT、增加 10 FF 和两个 RAMB36，DSP 数相同。

baseline 和 turnaround 最慢 setup 路径由运行控制到宏权重寄存器 CE，
数据路径分别为 13.405 ns 和 12.986 ns。cache 和 combined 最慢路径
由量化乘积寄存器到输出字节寄存器，分别为 13.580 ns 和 12.655 ns。
来源为各配置的 `critical_paths.rpt`、`timing.rpt`、`check_timing.rpt`、
`utilization.rpt`、`drc.rpt`、`route.rpt` 及
`impl_vivado.log`，本地原件在 `build/k7_matrix_<variant>/`。

### K7 板测与默认实现

2026-11-06（Asia/Shanghai）在同一 K7 V2.1 易失加载四版，确认 FPGA DONE
和各自的 USR_ACCESS 后采集 UART。每版比较四项任务共 16,128 字节，
另通过两次运行中热复位和重提。加速器板测周期与对应 SoC 仿真逐项一致。
同版历史记录使用当时的固件及实现，本表使用这次共同构建的实际周期。

|构建|M1 两种模式各自，周期 / µs|M125 阻塞，周期 / µs|M125 重叠，周期 / µs|
|---|---:|---:|---:|
|baseline|4,763 / 95.26|78,171 / 1,563.42|56,347 / 1,126.94|
|turnaround|4,523 / 90.46|48,171 / 963.42|29,323 / 586.46|
|cache|4,553 / 91.06|51,921 / 1,038.42|30,097 / 601.94|
|combined|4,523 / 90.46|48,171 / 963.42|26,719 / 534.38|

四版实际运行的同一 CPU 软件基线均为 M1 **23,013 拍 / 460.26 µs**，
M125 **2,749,533 拍 / 54.99066 ms**，每项零字节失配。对应 SoC 仿真
分别为 23,010 和 2,749,530 拍。板上软件计时比仿真多 3 拍。

**K7 默认选 combined。** 相对仅周转，两个 RAMB36 让 M125 重叠省
**2,604 拍 / 52.08 µs（8.88%）**，M1 与 M125 阻塞时间持平。缓存减少
14,000 个 M125 共享读，给同一存储口上的其他访问留下更多可用拍数。
组合版保持 50 MHz 收敛，最小 hold 裕量为 +0.067 ns。K7 上适合
默认启用。若部署侧 BRAM 紧张且共享 SRAM 为固定一拍、工作以 M1
或阻塞为主，选 `--variant turnaround` 可节省两块 BRAM，并保持这些
任务的周期。在已扫到的 2/4/8 拍响应点，缓存从 M1 起即可降低周期，
随 M 和存储等待增大收益更明显。独立 RTL 核仍默认仅周转，板级默认
由 `tools/k7.py` 明确选择组合配置。

完整逐项结果由 [精选证据](evidence/sram_cache_matrix_2026-11-06/) 生成，
其中共享读和本地端口次数来自 SoC RTL 仿真，实板周期、写提交数和
软件计数来自 UART。硬件、固件和 SRAM 的摘要分别随配置及公共元数据保存。

### 复现

独立 RTL 无需 SoC。要完整复现四版固定扫参以及可变等待，逐版执行并保存
CSV，防止下一版覆盖同名输出。真实数据集第一次按 README 导出 tensor23。

```powershell
$variants = 'baseline','turnaround','cache','combined'
New-Item -ItemType Directory -Force build/matrix_sim | Out-Null
foreach ($v in $variants) {
    python tools/run.py --simulator questa --dataset matrix --memory fixed --sweep-latency --variant $v
    if ($LASTEXITCODE -ne 0) { throw "Fixed RTL failed for $v" }
    Copy-Item -LiteralPath build/fixed_results.csv -Destination "build/matrix_sim/$v.csv"
    python tools/run.py --simulator questa --dataset real --variant $v
    if ($LASTEXITCODE -ne 0) { throw "Variable RTL failed for $v" }
    Copy-Item -LiteralPath build/results.csv -Destination "build/matrix_sim/${v}_real.csv"
}
```

K7 使用 Vivado 2023.2、`xc7k325tffg900-2`、Questa 2024.1 和 xPack
GCC 15.2.0。按 [板级依赖](BOARD_K7.md) 接入授权的 JYDD CPU/UART。
准备一次并复制相同的固件、SRAM、CPU 同步复位生成副本和元数据。

```powershell
python tools/k7.py prepare --variant baseline --cpu-source $cpuSrc --gcc-bin $rvBin
if ($LASTEXITCODE -ne 0) { throw 'Firmware preparation failed' }
foreach ($v in 'turnaround','cache','combined') {
    $dest = "build/k7_matrix_$v"
    New-Item -ItemType Directory -Force $dest | Out-Null
    Copy-Item -LiteralPath build/k7_matrix_baseline/build_metadata.json,build/k7_matrix_baseline/firmware.mem,build/k7_matrix_baseline/sram.mem,build/k7_matrix_baseline/cpu_include -Destination $dest -Recurse -Force
}
foreach ($v in $variants) {
    python tools/k7.py sim --variant $v --cpu-source $cpuSrc
    if ($LASTEXITCODE -ne 0) { throw "SoC simulation failed for $v" }
    python tools/k7.py impl --variant $v --cpu-source $cpuSrc
    if ($LASTEXITCODE -ne 0) { throw "K7 implementation failed for $v" }
}
# JTAG 易失加载，按板卡实际串号和串口填写
foreach ($v in $variants) {
    python tools/k7.py program --variant $v --jtag $jtagSerial --port $serialPort
    if ($LASTEXITCODE -ne 0) { throw "Board run failed for $v" }
}
python tools/compare_arch.py docs/evidence/sram_cache_matrix_2026-11-06 --capture build
```

只用公开的精选证据即可生成 CSV，无需 JYDD 依赖、位流或工具安装目录。

```bash
python3 tools/compare_arch.py docs/evidence/sram_cache_matrix_2026-11-06
```
