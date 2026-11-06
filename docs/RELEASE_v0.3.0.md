# v0.3.0

推荐稳定版本。两层 INT8 pointwise 可由真实 Ibex RV32IM 固件
一次提交。CI 使用同一入口验证 M1，中间和最终输出同时受固件与
宿主 golden 检查。M125 用同一入口运行完整双层任务。

```bash
python3 tools/run_ibex.py
python3 tools/run_ibex.py --m 125
```

开放复现使用 Ubuntu 24.04 或 WSL、Verilator、RV32IM GCC 和固定
Ibex 上游。运行结果包括两个 INT8 文件、周期与流量 JSON、CPU
执行轨迹。[依赖与架构](IBEX.md)

2026-11-06 的同位流 K7 50 MHz 板测中，M125 的 CPU 两次 START
和最终链式路径分别为 47,197 和 39,730 拍，延迟减少 15.82%。
相对提前回放，最后一步提前写回减少 1,501 拍。M1/M125 两层
均逐字节通过 golden。[六路径板测及计时窗口](TWO_LAYER_COMPARISON.md)

K7 双层复现使用 `python tools/k7.py prepare --two-layer --variant banked-early-write`，
再按同一配置仿真、布线或上板。板级实现需要授权取得的 JYDD CPU/UART、Vivado
和对应板卡。开放 Ibex 示例和独立 RTL 回归使用各自的工具。
[板级命令与依赖](INTERLAYER_WRITEBACK.md) ·
[第三方来源与许可](THIRD_PARTY.md) · [五分钟设计讲解](DESIGN_TALK.md)

历史 [v0.1.0](https://github.com/zlsjtj/riscv-cim-accelerator/releases/tag/v0.1.0)
与 [v0.2.0-rc.1](https://github.com/zlsjtj/riscv-cim-accelerator/releases/tag/v0.2.0-rc.1)
继续对应其原始提交与证据。
