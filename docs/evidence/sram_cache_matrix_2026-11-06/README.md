# 四版对照证据 · 2026-11-06

RTL、固件、构建选项与 CI 的对照源码为 `0adaca2`。四版使用同一
Questa 2024.1、Vivado 2023.2、xPack GCC 15.2.0 和 K7 V2.1。
板测在 Asia/Shanghai 日期下记录。原始完整构建输出分别位于本地
`build/k7_matrix_<variant>/` 和 `build/matrix_sim/`。

|文件|来源|
|---|---|
|`common.json`|准备阶段的 CPU 输入文件、生成镜像、tensor23、golden 和器件摘要|
|`<variant>/fixed.csv`|独立 RTL 固定延迟，每版 32 项|
|`<variant>/real.csv`|独立 RTL 可变等待和真实数据集，每版 22 项|
|`<variant>/traffic.csv`|SoC RTL 各任务的共享端口握手、本地 RAM 访问及周期|
|`<variant>/soc.json`|从 SoC RTL 仿真串口提取的任务、复位和软件结果|
|`<variant>/uart.txt`|实板原始 UART 文本|
|`<variant>/board.json`|从实板 UART 提取的任务、复位、软件结果及位流标识|
|`<variant>/routed.json`|布线报告摘录、网表结构计数、位流标识和摘要|

采集时对照四版的公共输入摘要、板卡和 UART，核对编程位流摘要，
并逐项验证加速器及复位记录与 SoC 仿真一致。局部硬件设备序列号、
生成 CPU 副本、位流和 routed DCP 保留在本地。

生成结果表的命令见 [四版对照](../../SRAM_CACHE_MATRIX.md)。
