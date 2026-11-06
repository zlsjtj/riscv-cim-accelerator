# K7 V2.1 原型

本文保留 v0.1.0 的板级档案。请检出原发布标签执行其原位流步骤。新分支的
两版同频构建入口见 [共享 SRAM 请求周转](SRAM_TURNAROUND.md)。

板级设计依据用户提供的竞业达 K7 V2.1 资料。原理图
`xc7k325t-V2.1.pdf` 第4、5、12页给出 FPGA、200 MHz 参考振荡器和 CP2104
UART。教学 MiniRV XPR 指定 Vivado part `xc7k325tffg900-2`，其
`miniRV_clk.xdc` 指定 20 ns CPU 时钟。参考输入 AD12/AD11 同时与
`board.txt` 及已有板级 XDC 一致。串口输出 D17 与已有
`source/route_src/digital_twin_265.xdc` 一致。原理图检查和首次 JTAG 探测
分别保存在 `build/board_docs/` 和 `build/jtag_probe.log`。

教学包的学生版 `myCPU.sv` 与 SoC 顶层有未完成的模板。实测使用外部 JYDD
工程的完整实现，`--cpu-source` 指向其 `source/` 根。需要 `route_src/myCPU.sv`、
`route_src/uart.sv`，以及 `common/` 下的 `RF`、`Control`、`IMMGEN`、`CCTL`、
`ALU`、`ACTL`、`CSR`、`defines`、`myCPU_units`、`myCPU_m_ext`、`myCPU_bitmanip`
这 11 个 `.sv` 文件。当前依赖的许可和 SHA-256 见 [第三方说明](THIRD_PARTY.md)
和 [交付清单](V0.1_MANIFEST.json)。构建在输出目录的 `cpu_include/` 生成乘除
单元的同步复位副本，并将其置于包含路径首位。`sim` 和 `impl` 检查这些原件
及生成镜像和副本与 `prepare` 记录相同。板上程序以 RV32I/ILP32 构建，CPU 参数关闭 XPERM4 和
早发 DRAM 读请求。仿真中对原 CPU 的 RF、分支预测数组初始值使用
Questa vopt 7061 兼容选项。

`cim_k7_top.sv` 使用 MMCM 将 200 MHz 转为 50 MHz，CPU、CiM、SRAM 与
UART 共用此时钟。SRAM 控制和 CPU 使用由 50 MHz 时钟采样的复位。
串口输出使用 115200 8N1，通过 CP2104
送往主机。约束仅对异步串口输出端口设时序例外。加速器和 CPU 的内部
路径均以 50 MHz 检查。

|地址|用途|
|---|---|
|`0x80000000`|4K×32 指令 ROM|
|`0x80100000–0x8010ffff`|共享 64 KiB SRAM，含输入、权重、参数、输出、测试数据和栈|
|`0x80201000`|CiM 寄存器|
|`0x80201100/104`|UART 忙状态和写数据|
|`0x80201108`|本次板测的已提交写字数|
|`0x8020110c`|读取热复位次数，写 1 请求在任务中触发热复位|
|`0x80201110/114`|热复位前的 STATUS、复位沿读有效位与已提交写字数|

`cim_rv_system.sv` 使用一个 SRAM 端口做 CPU 同步读，另一个端口在
已暂存的 CPU 写和 CiM 请求间仲裁。CiM 写握手与 SRAM 提交在同一沿，
读数据与 `mem_rvalid` 对应下一拍。固件先把已经由独立参考生成的
tensor23、打包权重和参数从预装区域复制到工作地址，然后调用已有 C
驱动提交一次 START。固件轮询 DONE 后读取真实输出 SRAM，逐字节检查
golden，并检查写提交计数，最后通过 UART 报告每项计数和 `CIM_PASS`。

复位用例对每种调度模式先提交一个 M=125 任务。固件先用逐字取反的
golden 填充输出区，再在检测到 BUSY 和已有写提交后请求复位。硬件在
下一个 CiM 读请求被接受时安排一个时钟拍的复位，复位 CPU、CiM 和
适配器事务状态。MMCM、UART 串行器、SRAM 内容和复位事件记录独立保留。
重启的固件检查 STATUS、周期和写计数归零，并扫描整块输出确认仅保留
复位前已提交的字。随后立即重新提交同模式 M=125，再执行 M=1，
两项均逐字节比较。串口 `CIM_RESET` 依次打印模式、复位前 STATUS、
复位沿读响应有效、复位前写字数、复位后 STATUS、周期、写字数、SRAM
保留的结果字数和异常字数，数值格式均为八位十六进制。

## 构建与演示

从项目根目录执行。公开源码提供板级适配和构建入口，整板需要自行提供
获授权的外部 JYDD CPU/UART。先按 [README](../README.md) 导出 tensor23，准备
xPack GCC 15.2.0、Questa 2024.1 和 Vivado 2023.2。当前分支默认构建
`banked`，输出到 `build/k7_matrix_banked/`。使用 `--variant combined`
构建 32 位回放，也可用 `--out` 指定目录。准备、仿真、实现和加载须
使用同一配置和目录。[双 bank 与 32 位回放对照](BANKED_REPLAY.md)

```powershell
$cpuSrc = '<经授权的 JYDD 工程 source 目录>'
$rvBin = '<xPack GCC 的 bin 目录>'
$env:QUESTA_BIN = '<Questa 的 win64 目录>'
$env:VIVADO_BIN = '<Vivado 的 bin 目录>'
python tools/k7.py prepare --cpu-source $cpuSrc --gcc-bin $rvBin
python tools/k7.py sim --cpu-source $cpuSrc --trace-blocks
python tools/k7.py impl --cpu-source $cpuSrc
```

`impl` 输出路由状态、时序、资源、DRC 和约束检查，要求
`REQP-1839` 消失后生成位流。`sim --trace-blocks` 在同一输出目录写出
`block_trace.csv`，用来核对上下文分配、量化发射和写提交的周期。

板上演示只写易失配置。连接 JTAG 和 CP2104，关闭占用串口的终端。
设置实际 JTAG 序列号和 COM 号，再运行下列命令。`probe_jtag.tcl`
可用 Vivado batch 执行以识别目标，`python -m serial.tools.list_ports`
可在安装 pyserial 后列出串口。

```powershell
python -m pip install pyserial==3.5
$jtagSerial = '<实际 JTAG 序列号>'
$serialPort = '<实际 COM 号>'
python tools/k7.py program --jtag $jtagSerial --port $serialPort
```

脚本核对 FPGA 型号、位流摘要、JTAG DONE 和配置对应的 USR_ACCESS。
默认配置的标识为 `43494d44`。UART 115200 8N1 输出两条 `CIM_RESET`、
四条 `CIM_RESULT`、两条 RV32IM `CPU_RESULT` 和 `CIM_PASS`。
固件的启动串保留原先 scratchpad 实验的文字，配置以 JTAG 读回的
USR_ACCESS 为准。可用 M1 的 64 字节核对展示运行时配置生效。

原始量化流水版板测位流、日志和结果位于 `build/k7_qpipe/`。有权在本地
使用该归档时，从 `v0.1.0` 检出对应脚本，用新输出目录保留原始记录。

```powershell
python tools/k7.py program --out build/demo-v0.1 --bitstream build/k7_qpipe/cim_k7.bit --jtag $jtagSerial --port $serialPort
```

已通过热复位的旧 50 MHz 基线保存在 `build/k7_reset/`，首次 50 MHz 实测
归档保存在 `build/k7/`。所有本地位流的公开分发边界见 [第三方说明](THIRD_PARTY.md)。
性能计数取自
`CIM_CYCLES`，从任务 START 起算，覆盖权重和参数装载、输入读、计算和
最终 SRAM 写提交及 DONE。CPU 复制测试数据、固件比较与 UART 发送在计数窗口之外。

需要加载已通过热复位的基线位流时，可在项目根目录执行以下命令。

```powershell
& "$env:VIVADO_BIN/vivado.bat" -mode batch -source fpga/program_k7.tcl -tclargs $jtagSerial build/k7_reset/cim_k7.bit 43494d32
```
