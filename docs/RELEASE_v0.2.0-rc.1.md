# v0.2.0-rc.1 · K7 50 MHz 请求周转

候选基于公开分支 `upgrade/sram-turnaround` 的 `76194e4`。
同一上下文的输入字返回时发出下一字，保留单未决读合同和已就绪写回优先级。
该候选使用共享 SRAM 和原宏、量化器，支持 K=N=64、M=1..125 的
完整 INT8 pointwise 算子。

|K7 50 MHz 原板测|匹配基线|候选|延迟减少|
|---|---:|---:|---:|
|M1 阻塞、重叠各一项|4,764|4,524|5.04%|
|M125 阻塞|78,172|48,172|38.38%|
|M125 重叠|56,348|29,324|47.96%|

2026-11-06 原板测中，两版各通过四项任务的 16,128 字节比较及两次运行中
热复位、重新提交。任务窗口从 START 到最终 SRAM 写提交及 DONE。候选
WNS / WHS 为 +7.022 / +0.075 ns，整板使用 16 个 RAMB36、8 个 DSP。
资源、位流哈希及工具版本见 [请求周转对照](SRAM_TURNAROUND.md)。

[原 UART 基线](evidence/turnaround_rc_baseline_uart.txt) ·
[原 UART 候选](evidence/turnaround_rc_candidate_uart.txt) ·
[原对照 CSV](evidence/turnaround_rc_board_comparison.csv)

```bash
python3 tools/run.py --dataset synthetic --simulator iverilog
```

公开回归需要 Python 3、G++ 和 Icarus Verilog。完整 K7 流程需要用户
提供有权使用的 JYDD CPU/UART，使用 `tools/k7.py` 及
[板级接入说明](BOARD_K7.md) 在本地生成整板位流。独立 RTL 无需这些源码。

[`v0.1.0`](RELEASE_v0.1.md) 及其原始证据继续可检出。输入缓存与相同
RV32IM 固件下的四版对照在
[`upgrade/sram-cache-matrix`](https://github.com/zlsjtj/riscv-cim-accelerator/tree/upgrade/sram-cache-matrix)。
