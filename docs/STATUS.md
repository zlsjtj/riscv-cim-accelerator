# 当前项目状态

## 稳定版 v0.4.0

[GitHub Release](https://github.com/zlsjtj/riscv-cim-accelerator/releases/tag/v0.4.0) ·
[英文首页](../README.md) · [中文首页](../README.zh-CN.md) · [复现入口](REPRODUCE.md)

真实 KWS 子图使用固定 INT8 模型的 PW(op2) → CPU DW(op3) → PW(op4)。
Stop、Left 两条公开量化 MFCC 输入均从真实 tensor23 开始。混合路径两次
独立 START，中间数据经共享 SRAM 交给 CPU DW 和第二个 PW。

| 验证 | 已完成 |
| --- | --- |
| TensorFlow 2.16.1 | 独立顺序整数 MAC，Stop 和 Left 共 48,000 个输出字节匹配 |
| 开放 Ibex RTL 仿真 | 真实 RV32IM 固件，同 ELF 运行两样本的混合和纯 CPU 路径，正式结果和独立诊断匹配 |
| 原始 K7 实测（2026-11-07） | 50 MHz，混合约 18.68 ms，较同固件纯 RV32IM C 快 6.83–6.84×。独立诊断 96,000 字节零失配 |

K7 计时从输入恢复后开始，到最终输出末字可读。四个正式窗口各另
核对 8,000 个最终字节，比较与 UART 在窗口外。K7 源码
[`a37a911`](https://github.com/zlsjtj/riscv-cim-accelerator/commit/a37a911)、
证据 [`6002694`](https://github.com/zlsjtj/riscv-cim-accelerator/commit/6002694)，
位流读回 `43494d4a`。[逐阶段数据、布局和原始证据](KWS_SUBGRAPH.md#k7-50-mhz-实测)

## 复现和边界

- 开放 CPU 快速入口为 `python3 tools/run_ibex.py`，运行合成数据的双 PW M1。
  完整真实子图先执行 `python tools/prepare_kws.py`，再执行
  `python3 tools/run_ibex.py --kws build/kws_fixture --diagnostic`。
  [环境和输出](REPRODUCE.md)
- K7 使用 Vivado 2023.2、授权的本地 JYDD CPU/UART、xPack GCC 15.2.0 和板卡。
  本轮未重新实现或烧板，保留原始记录。K7 混合 PW1 比对应 Questa
  SoC 窗口多 3 拍，具体事件尚未定位。[板级步骤](KWS_SUBGRAPH.md#复现)
- 当前范围为可综合低位数字宏代理和三个真实算子的软硬件子图。
  两样本诊断对应所列张量，完整 KWS 分类准确率、模拟宏特性和物理能效超出本版范围。

## 后续可选

CPU DW 占 K7 混合窗口约 94.94%。以原始窗口为对照，若从约 887,000
降到 710,000 拍，估计可省约 3.55 ms。更多样本、提频、DW 硬件和
整网部署也属于后续工作。[计算依据](KWS_SUBGRAPH.md#端到端瓶颈)

[完整历史索引与原始状态记录](STATUS_HISTORY.md) · [发布检查记录](CLOSEOUT.md)
