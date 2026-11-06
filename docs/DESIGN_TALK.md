# 五分钟设计讲解

## 0:00–0:45 · 从真实输入走一遍 SRAM

tensor23 从 8,000 字节输入备份恢复到 A。PW(op2) 写 B，RV32IM CPU
从 B 读真实 PW 输出并做 3×3 DW(op3)，写回 A。PW(op4) 再从 A
读真实 DW 输出，最终写 B。混合路径用驱动各提交一次 START，
纯 CPU 路径用同一个 ELF 中的 C PW。中间 golden 在宿主机，供
诊断工具核对。用 [架构图](assets/architecture.svg) 指出两个 START
和三次缓冲区交接。[工作区地址和权重排布](KWS_SUBGRAPH.md#sram-布局)

## 0:45–1:45 · 低位宏如何得到 INT32

权重 tile 按 K 和 lane 打包。对每个 INT8 权重，
`w = unsigned(w_lo) + 16 × signed(w_hi)`。真实子图的激活
零点为 −128，因此中心化后的 `q + 128` 可拆成两个无符号 nibble。
[cim_macro.sv](../rtl/cim_macro.sv) 按四个位平面输入计算低位部分和，
[cim_accel.sv](../rtl/cim_accel.sv) 再按 1、16、16、256 的交叉权重
重建 INT32 累加。独立参考用直接 MAC 验证同一个整数合同。

## 1:45–2:45 · 先预约，再发射

宏返回不可暂停。调度前检查 `raw_valid | raw_reserved`，为在途
结果预约一个槽。两个上下文各自保有行号、部分和、量化和写回状态。
SRAM 未接受请求时，已登记的地址和写数据保持稳定。举一个握手顺序：
末字请求在背压期间保留，`write_commit && req_last` 成立后释放
该行上下文，任务最后一次写提交且排空后才置 DONE。配合
[RTL](../rtl/cim_accel.sv) 指出预约判断和提交条件。

## 2:45–3:30 · 量化与 CPU 交接

[requant.sv](../rtl/requant.sv) 用逐通道乘数和 shift，依次执行定点高半
乘法的舍入、右移的整数舍入，再加输出零点并限制到融合 ReLU 的
INT8 范围。bias 已进入累加。CPU 等待写回，再从 SRAM 读到下一
算子。正式计时涵盖提交、轮询、数据交接和最终末字读取，比较与
输出在计时窗口之外。[计时与诊断](KWS_SUBGRAPH.md#计时和诊断)

## 3:30–5:00 · 用实测回答收益和瓶颈

同一 K7 50 MHz 位流、ELF、SRAM 镜像，Stop 和 Left 的混合路径约
18.68 ms，纯 RV32IM C 约 127.70 ms，速度比为 6.83–6.84×。
两样本 × 两路径 × 三层 × 8,000 字节，共 96,000 字节来自独立诊断，
逐字节与 TensorFlow 2.16.1 一致。CPU DW 约 887,000 拍，占混合窗口
约 94.94%。若将它降到 710,000 拍，预计可省约 3.55 ms。

演示可从 [归档 UART 回放](DEMO.md) 核对四个窗口，或执行
`python3 tools/run_ibex.py` 演示开放 CPU 的双 PW M1。Ibex 周期与
K7 指标分别查看。[原始 K7 数据](evidence/kws_subgraph/k7_board.json) ·
[完整子图和复现](REPRODUCE.md)
