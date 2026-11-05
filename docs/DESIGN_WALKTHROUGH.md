# 50 MHz v0.1 设计讲解

## 从 SRAM 到一个 8 通道输出块

`cim_rv_system` 把 CPU 的 MMIO 访问交给 `cim_accel`，并仲裁 CPU 与 CiM 的
共享 SRAM 访问。固件写配置和一次 START。`cim_accel` 锁存 M、MODE 和四个
基址，在每个 tile 装载 8 通道参数及 512 B 权重。该 tile 的权重驻留在宏内，
对 M 个输入位置各计算一个 8 通道块，然后排空换 tile。

`cim_accel.sv` 的 `RD_INPUT` 把 INT8 输入翻转 MSB，等价于 `u=q+128`。
`uL`、`uH` 均为 U4。权重 `w=wL+16*wH`，其中 `wL` 为 U4、`wH` 为 S4。
`cim_macro.sv` 的相邻列分别实现这两种权重类型。一次 A4 发射按 bit3 到 bit0
送入 64 位平面，每列每拍以 `2*acc+plane_sum` 更新。K=64 时偶数列点积
最大为 14,400，需要 U14。奇数列范围 −7,680 到 6,720，需要 S14。

外围对两种原生结果分别零扩展、符号扩展到 INT32，再计算 `Dlo+(Dhi<<4)`。
两轮输入分片各得到一个贡献，最后计算 `low+(high<<4)+bias`。例如 `q=-111`
得到 `u=17`，`w=-17` 的两个 nibble 是 `15` 和 `-2`，两轮的贡献均为
`15+16*(-2)=-17`，重建点积为 `-17+16*(-17)=-289`。bias 在完整重建后加一次。

`requant.sv` 首先捕获 64 位有符号乘积、POT 指数及极值饱和标记。第一步
舍入是带符号 nudge 的高乘，除以 `2^31` 时向零截断，极值特例钳为
`INT32_MAX`。第二步比较低位余数与按符号调整的阈值，完成 `RoundingDivideByPOT`。
最后在宽位域减 128 并饱和至 INT8。输出零点 −128 同时是该层 ReLU 的下限。
Golden 用直接整数 MAC，先与固定 TensorFlow/gemmlowp 原函数交叉验证。

## 结果预约与提交

每个输入槽绑定一个块上下文。阻塞模式只准一个块存活，重叠模式可存活两个。
宏 E0 接受 start，E1–E4 采样四个位平面，E4 后输出 valid，外围在 E5
消费。宏结果没有 ready，控制器在每次 `mac_start` 就设置
`raw_reserved[sched_slot]` 并保存上下文及高低分片标签。返回时该槽从 reserved
转为 valid。两个原生槽的占用与预约之和始终最多为 2，槽满只停新发射。

弹出低分片后 `partial` 仍属当前上下文。高分片处理后 `recon_done` 允许共享量化
发射通道。`quant_index` 统计发射数，`q_result_valid/ctx/channel` 延迟一拍
跟踪实际写入 `output_bytes` 的结果。通道 7 落入缓冲后才设置 `output_ready`。
两次 32 位写均实际提交后，`req_last` 路径清除 `live`，此时输入槽和上下文
才可重用。`cim_rv_system` 的 `cim_access && mem_write` 与 SRAM 提交同沿。

最后一个块提交后，控制器确认所有上下文、宏、预约、读响应、请求和量化有效位
均排空才置 sticky DONE。新 START 或 ACK 可清除 DONE。热复位使 `run_n` 拉低，
SRAM 已提交内容和复位记录保留，旧读响应被丢弃，BUSY、DONE、量化有效位和
事务计数清空。固件重启后重新装载并提交，不能从中止点续跑。

## WNS 与任务周期是两件事

旧最差 setup 路径穿过上下文选择、乘法、双舍入及输出寄存器。乘积处切一刀后，
两段数据路径分别为 9.785 和 12.327 ns，旧路径为 18.836 ns。整板最差路径
移到运行使能至宏权重写使能，WNS 从 +0.842 ns 改善至 +5.885 ns。时钟仍为
20 ns，量化通道发射 II 仍为 1，单通道结果落点延后一拍。

诊断在同一 CPU、固件、SRAM 镜像和测试平台下运行最终 RTL 与只旁路量化
乘积寄存器的临时对照。旁路让通道结果在发射沿直接落入缓冲。它的两次复位和
四项完整任务通过，任务计数与保存的旧板测逐项一致。这是行为对照，旧位流的
物理时序仍以原布线报告为准。

|M125，tile 0 的例子|通道 7 发射（旁路 → v0.1）|末字提交（旁路 → v0.1）|该块之后的动作|
|---|---:|---:|---|
|阻塞，p=0|593 → 593|597 → 598|p=1 分配从 598 延到 599|
|重叠，p=0|593 → 593|598 → 598|发射后一拍 `rd_pending=1`，两版均等待输入读响应|
|重叠，p=124|7,041 → 7,041|7,045 → 7,046|发射后一拍无读未决，tile 排空等末字提交|

**阻塞 +1,000 拍。** 每个块独占上下文。全部 1,000 个块从通道 7 发射到
末字提交的间隔均由 4 拍变成 5 拍。末字提交才释放 `live`，下一块或下一个
tile 因此继承这一拍延迟。M=1 每 tile 只有一个块，两种模式均累计 +8 拍。

**重叠 +8 拍。** M125 的 992 个非末块在通道 7 发射后第一拍均有
`rd_pending=1`。写请求生成必须等 `!rd_pending && !mem_valid`，因此旧版在
这一拍也无法启动写回。992 个块的发射到末字提交间隔两版均为 5 拍。每 tile
最后一个块发射后一拍无待返回读，末字提交间隔由 4 拍变 5 拍。跨 tile 排空
共累积 8 拍。该遮蔽比例对应本次 K7 SRAM 时序与任务，外部等待模式变化时需
重新测量。

干净目录 `python tools/k7.py sim --cpu-source $cpuSrc --trace-blocks` 生成
`build/k7_v0.1/block_trace.csv`。本轮诊断原始文件见
`build/repro-v0.1/build/trace_comparison.log`、`trace_arbitration.log`，
旁路操作和日志位于 `build/repro-v0.1/diagnose_bypass.py` 与
`build/repro-v0.1/build/quant-bypass/`。此前存档主要为文本日志，本轮另导出
最终版和旁路版的短 VCD 片段 `quant_overlap.vcd`，位于各自 `k7_v0.1/` 构建目录。
观察 `q_valid`、`q_result_valid`、`output_ready`、`rd_pending`、`cim_access`
和 `req_last` 可分别定位发射、量化在途、写可发射、读未决和最终提交。
