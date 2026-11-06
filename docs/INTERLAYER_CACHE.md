# 两层 pointwise 的中间激活保留

本分支从 `upgrade/two-layer-pointwise` 的 `6c18d1e` 开始。两层
K=N=64，M1/M125 使用同一 tensor23、固定的第二层合成权重和独立
直接 MAC golden。[数据来源和两层接口](TWO_LAYER.md)

## 基线成本与容量选择

先从原链式版本的完整 SoC 仿真提取第二层第一个 tile 的时间线。
RUN 计入该 tile 的输入、计算及写回阶段。输入等待只计已分配输入
槽未齐、宏空闲且原生结果槽有容量的拍。

|M|第二层首次中间 SRAM 读（32 位字）|第二层首 tile RUN|输入等待|首个宏启动相对 RUN 首拍|
|---|---:|---:|---:|---:|
|1|16|45|18|19|
|125|2,000|3,145|1,878|19|

原输入缓存必须为第一层各 tile 保留原输入。第一层按输出通道 tile
依次产生中间结果，直接写回原输入缓存会提前覆盖后续 tile 要读的字。
新增独立的偶、奇两个 1,024×32 位 bank，每个映射到一块 RAMB36，
容量 8 KiB，可覆盖最多 125×64 个 INT8 值。

带保留选项的链式 START 写 CONTROL 值 `0x0d`。第一层每次 SRAM
写在实际接受的同一边沿写入保留 bank，字索引为
`16 × position + 2 × tile + req_last`。第一层最后一字提交且流水
排空后，第二层包括 tile 0 在内均以 64 位本地回放取输入。
中间和最终 SRAM 写回地址仍为 `0x80106000` 和 `0x80108000`。复位清除当前任务的
保留和回放控制，下一次保留任务用实际提交的写逐字覆盖所用地址。

## 同口径对照

`banked-retain` 的同一个位流和固件依次运行两次 START、链式重读、
两层 RV32IM C 和链式保留。两个链式命令在定时前选好标志，使用同一个
驱动调用点。起点为输入就绪后的计时器启动提交，终点为 CPU 读过
最终结果后的停表提交。黄金比较与 UART 在计时窗口外。第一层中间
输出和第二层最终输出在每条路径结束后分别逐字节比较。

## SoC 验证和访问量

Questa 2024.1 验证保留写和 SRAM 写的接受沿及地址逐字一致。定向测试
覆盖写请求背压期间的禁止提前保留，以及第二层回放结果在途时复位。
M1/M125 的八组端到端任务均与两级 golden 逐字节匹配，候选的单层
真实数据集回归另通过 22 项任务。

以下为最终固件的 SoC 握手计数，单位为 32 位字。两次 START 的
加速器 SRAM 读写次数与链式重读一致。

|M|链式重读 SRAM 读 / 写|链式保留 SRAM 读 / 写|第二层中间 SRAM 读|同拍保留写|
|---|---:|---:|---:|---:|
|1|2,464 / 32|2,448 / 32|16 → 0|16|
|125|6,432 / 4,000|4,432 / 4,000|2,000 → 0|2,000|

M125 加速器共享 SRAM 读减少 31.09%。第二层首 tile 的 RUN 从
3,145 降至 2,269 拍，宏空闲且等输入从 1,878 降至 630 拍，
首个宏启动相对 RUN 首拍从第 19 拍提前到第 11 拍。第二层首 tile
节省的 876 拍与链式核内总周期差一致。M1 对应首 tile 从 45 降至
37 拍，SoC 仿真的端到端计时仍为 9,607 拍。

## K7 50 MHz 资源和时序

资源以原链式位流的归档布线报告和本轮 `banked-retain` 布线报告为准。
本轮位流内的运行时对照共用同一网表。

|布线指标|原链式位流 `43494d45`|本轮位流 `43494d46`|
|---|---:|---:|
|整板 LUT / FF|16,459 / 11,244|16,248 / 11,236|
|加速器 LUT / FF|10,714 / 8,229|10,470 / 8,221|
|整板 RAMB36 / DSP|18 / 8|20 / 8|
|层间保留 RAMB36|0|2|
|WNS / WHS (ns)|+7.019 / +0.029|+7.173 / +0.050|

原输入缓存仍用两块 RAMB36。LUT/FF 是各自完整网表结果，包含综合映射
差异。候选内部未约束端点、路由错误、DRC Error 和 `REQP-1839`
均为 0。20 条 DRC 建议来自 DSP 流水。最慢 setup 数据路径从
`plane_index_reg[0]` 到宏结果寄存器，数据路径延迟 12.577 ns。

## 同板实测

2026-11-06，在同一 K7 V2.1 易失加载 `43494d46`。四条路径分别执行
M1/M125，每次核对中间与最终输出，合计比较 64,512 个 INT8 字节，
零失配。计时口径为输入就绪到最终结果可读。

|M|两次 START|链式 SRAM 重读|链式片上保留|两层 RV32IM C|
|---|---:|---:|---:|---:|
|1|9,772 拍 / 195.44 µs|9,610 拍 / 192.20 µs|9,610 拍 / 192.20 µs|45,995 拍 / 919.90 µs|
|125|47,196 拍 / 943.92 µs|47,058 拍 / 941.16 µs|46,177 拍 / 923.54 µs|5,493,594 拍 / 109.87188 ms|

片上保留让 M125 相对链式重读少 881 拍（17.62 µs、1.87%），
M1 的板测窗口相同。两个链式路径的板测绝对周期都比 SoC 仿真多
3 拍，链式路径之间的差值一致。共享 SRAM 访问量取自 SoC 握手计数。
保留作为显式构建和提交选项，便于按可用 BRAM 和任务大小选择。
源码为 `a831757`。[UART、布线、输入摘要及对照表](evidence/interlayer_cache_2026-11-06/)

## 复现

按 [板级依赖](BOARD_K7.md) 配置本机工具及经校验的真实激活。

```powershell
$out = 'build/k7_interlayer_final'
python tools/run.py --simulator questa --dataset real --variant banked-retain
python tools/k7.py prepare --two-layer --variant banked-retain --out $out --cpu-source $cpuSrc --gcc-bin $rvBin
python tools/k7.py sim --two-layer --variant banked-retain --out $out --profile-tasks --cpu-source $cpuSrc
python tools/profile_replay.py --second-tile0 "$out/task_edges.csv"
python tools/k7.py impl --two-layer --variant banked-retain --out $out --cpu-source $cpuSrc
python tools/k7.py program --two-layer --variant banked-retain --out $out --jtag $jtagSerial --port $serialPort
```

原链式时间线可在其构建目录用
`python tools/profile_replay.py --second-tile0 build/k7_two_layer/task_edges.csv`
复算。候选 UART 的 `CHAIN_RESULT` 路径编号 3 为链式保留，其余
编号沿用原链式基准。原始逐拍数据保存在各构建目录。
