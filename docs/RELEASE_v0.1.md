# 50 MHz v0.1.0 发布说明

v0.1 是 K7 V2.1 上运行的单层 FPGA 原型，固定 K=N=64、运行时 M=1..125。
RV32I 固件通过 MMIO 一次启动，数字外围自主执行两轮低位宏操作、INT32 重建、
逐通道双舍入和最终 INT8 写回。宏代理实现 64 行、16 个 W4 输出列和 A4 位串行
运算。证据覆盖数字代理与外围、单层数值和板级事务；整网 KWS、模拟宏物理实现和
功耗/能效不在首版交付范围。

## 版本和产物

|标识|本地归档|用途|
|---|---|---|
|v0.1.0，`USR_ACCESS=43494d33`|`build/k7_qpipe/`|2026-11-05 实测的 50 MHz 最终版，量化乘积一级流水|
|`USR_ACCESS=43494d32`|`build/k7_reset/`|50 MHz 同固件、同数据的热复位对照|
|`USR_ACCESS=43494d31`|`build/k7/`|最早 50 MHz 板测归档|
|重建及独立验证|`build/repro-v0.1/`|源码独立复制后重新生成的参考、RTL、固件和 SoC 证据|

已测 `cim_k7.bit` 的 SHA-256 是
`b2c18a796ce1559535d6723b9dbb4ac84b02f081a6ff34215457367bc6c67805`。
[清单](V0.1_MANIFEST.json) 冻结当前可构建源码、工具版本、外部依赖、固定样本、
产物及报告摘要。原 Vivado 和板测归档早于本清单，清单中的项目源码摘要是本轮
冻结值。独立复现直接核对了外部源文件、固件执行镜像和 SRAM 初始化镜像，
整板实测结论绑定原 `43494d33` 位流及其原始报告。干净目录生成的 `.bit`
与原件长度相同，两个头部只在生成时间字段不同，配置载荷逐字节相同。
载荷 SHA-256 为 `425c10120359f63d74f1abde22aa5d3dee66c7a323b5e05fcb621963724c729d`。

## 同一新版的实测对照

|M|调度|`CIM_CYCLES`|用时（µs）|逐字节匹配|SRAM 提交字数|
|---|---|---:|---:|---:|---:|
|1|阻塞|4,764|95.28|64 / 64|16|
|1|重叠|4,764|95.28|64 / 64|16|
|125|阻塞|78,172|1,563.44|8,000 / 8,000|2,000|
|125|重叠|56,348|1,126.96|8,000 / 8,000|2,000|

同一新版、50 MHz、M125 的任务延迟减少 **27.9179%**，速度比 **1.3873×**。
计时从 START 到最终 SRAM 写提交及 DONE，包含 8 个 tile 的权重和参数装载、
激活读、计算及排空。CPU 预装、比较和 UART 输出在窗口之外。两次 M125
运行中热复位均捕获旧读响应，复位前已提交 2 字。重启后 BUSY/DONE、周期和
提交计数归零，整块输出仅保留那 2 字。随后重提 M125 和 M1，结果逐字节通过。
原始证据为 `board_uart.log`、`board_results.json`、`program_vivado.log`。
公开版附上原 UART 文本和同版 RTL 回归的周期、存储事务计数。
[2026-11-05 UART](evidence/k7_uart_2026-11-05.txt) · [RTL 回归 CSV](evidence/rtl_results.csv)

量化流水化是另一组比较。相同 50 MHz 下，M1 两模式各增加 8 拍，M125 阻塞
增加 1,000 拍，M125 重叠增加 8 拍。主要已验证收益是 WNS 从 +0.842 ns
变为 +5.885 ns。完整比较见 `board_comparison.json`，周期归因见
[设计讲解](DESIGN_WALKTHROUGH.md)。

## 最终位流的布线证据

报告均来自 `build/k7_qpipe/` 的原板测构建，Vivado 2023.2 build 4029153，
器件 `xc7k325tffg900-2`，顶层 `cim_k7_top`。同一 routed DCP 可复核这些指标。

|项|v0.1 数值及位置|原报告|
|---|---|---|
|Setup / hold|WNS +5.885 ns，WHS +0.038 ns，TNS/THS 0，失败端点均为 0|`timing.rpt`|
|时钟和约束覆盖|参考时钟 5 ns，MMCM 生成 `raw_clk` 20 ns；无时钟寄存器和内部未约束端点均为 0；`uart_tx` 是唯一无输出延迟的端口，XDC 将该异步串行线设为 false path|`timing.rpt`、`check_timing.rpt`、`fpga/cim_k7.xdc`|
|布线及 DRC|28,266 / 28,266 可布线网完成，路由错误 0；DRC 0 错误、0 条 `REQP-1839`，20 条 DSP 流水建议|`route.rpt`、`drc.rpt`|
|整板最差 setup 路径|`system_run_reg/C` 到 `system/accel/macro_unit/weights_reg[39][10][3]/CE`，数据路径 13.819 ns，其中路由 13.354 ns|`critical_paths.rpt`|
|量化分段|乘积前 9.785 ns，乘积后 12.327 ns，分段 slack +9.259 / +7.246 ns|原 `routed.dcp` 的 `quant_product_paths.rpt`、`quant_writeback_paths.rpt`|

|资源范围|LUT|FF|RAMB36|DSP|
|---|---:|---:|---:|---:|
|整板 `cim_k7_top`|15,826|10,956|16|8|
|加速器 `system/accel`，含宏和量化|10,735|7,974|0|4|
|W4A4 宏代理 `macro_unit`|7,523|4,532|0|0|
|数字外围，含量化（加速器减宏）|3,212|3,442|0|4|
|外围本地逻辑 `(accel)`，层次报告行|2,390|3,401|0|0|
|共享量化 `quant_unit`，层次报告行|823|41|0|4|

来源为 routed `utilization.rpt`，LUT 使用 `Total LUTs`。Vivado 报告的两条
外围子行 LUT 合计为 3,213，比从父行减宏所得的 3,212 多 1。表中分别保留
原行与差值。两个调度模式共用一份网表。

## 独立目录复现记录

新建 `build/repro-v0.1/`，仅复制源、文档和入口，起始没有 `build/`、仿真库、
模型、样本、环境、生成版 CPU 文件或位流。Windows x64、Python 3.12.0、
G++ 9.3.0、Questa 2024.1、xPack RV GCC 15.2.0-1、Vivado 2023.2。
环境变量和 CPU/GCC 参数的设置方法见 [README](../README.md) 与
[板级说明](BOARD_K7.md)。下表日志相对于独立目录的 `build/`。

|执行命令|结果与日志|
|---|---|
|`python -m pip install --target build/deps_python -r tools/requirements-model.txt`|PASS，模型解析依赖安装。受限进程 DNS 首次失败，具备网络权限后重试通过。`install-model-network.log`|
|`python -m venv build/tf_env`，`build/tf_env/Scripts/python.exe -m pip install -r tools/requirements-runtime.txt`|PASS，新建隔离环境，安装 TensorFlow 2.16.1、NumPy 1.26.4。`install-runtime-network.log`、`tf_environment.txt`|
|`python tools/run.py --simulator questa`|PASS，另一份空目录验证快速开始，8 个合成任务、32,256 字节匹配。`public-rtl/build/quick-start.log`|
|`python tools/run.py --real-activations --simulator questa`|PASS，重新下载固定上游，3,220 次官方舍入和 70 次 scale 核对，主机 8,000 字节交叉核对，RTL 16 任务 / 64,512 字节，0 错误。`repro-rtl.log`、`simulation.log`、`results.csv`|
|`python tools/synth.py --driver`|PASS，宿主 C 编译及驱动打包、参数和范围检查。`repro-driver.log`|
|`python tools/k7.py prepare --cpu-source $cpuSrc --gcc-bin $rvBin`|PASS，重新生成 RV32I/ILP32 固件、镜像及同步复位副本。`repro-prepare.log`、`k7_v0.1/build_metadata.json`|
|`python tools/k7.py sim --cpu-source $cpuSrc --trace-blocks`|PASS，四项任务与两次复位均与原板测完全一致。外部 CPU 有 3 条端口类型告警，沿用初始化数组的 Questa 7061 兼容设置。`repro-soc.log`、`k7_v0.1/block_trace.csv`|
|`python tools/k7.py impl --cpu-source $cpuSrc`|PASS，干净目录生成 50 MHz 位流，WNS +5.885 ns、WHS +0.038 ns，配置载荷与原板测位流逐字节相同。`repro-impl.log`、`k7_v0.1/bitstream_metadata.json`、`bitstream_comparison.log`|
|`vivado -mode batch -nojournal -log audit.log -source audit.tcl -tclargs <原 routed.dcp>`|PASS，重出 setup/hold、约束、分层资源、DRC、布线报告，关键指标与原报告相同。`dcp-audit/console.log` 及同目录报告|
|对故意更改的生成版 M 单元执行 `k7.py sim --out build/guard-check`|PASS，在编译前拒绝，正常构建与归档均未改动。`guard-check.log`|

`firmware.mem`、`sram.mem`、`text.bin`、`data.bin` 及生成的 `myCPU_m_ext.sv`
与已测版逐字节相同，ELF 的 `.strtab` 不同。外部 CPU/UART 全部源码摘要一致。
RTL 的任务及稳态 CSV 与已测版同期归档完全相同。见 `artifact_check.log`。
干净重建验证配置载荷。实板结果来自 2026-11-05 的原始 `43494d33` 运行。

## 公开范围

独立 IP 的原创内容按 Apache-2.0 发布。独立 RTL 回归仅依赖 Python、G++、
Questa 和通过固定 URL 获取的参考函数，完整整板流程还需要用户提供有明确
获取与使用授权的 JYDD CPU/UART。板测 bit/DCP、外部源文件、生成副本、
第三方样本及张量留在本地。文中的 `build/` 归档路径供追踪原始证据，
公开版本保留摘要、哈希和精选文本证据。
详见 [第三方说明](THIRD_PARTY.md) 与 [板上演示](BOARD_K7.md)。

可选后续工作是独立频点的时序优化和板测。提频及 MMCM 失锁/重锁均为 NOT_RUN。
