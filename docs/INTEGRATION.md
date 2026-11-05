# 软件与 FPGA 接入合同

`sw/cim.h` 的寄存器偏移对应 RTL 的简单配置总线。配置口每次
`cfg_valid && cfg_ready` 为一次传输；上层适配器必须保证读返回与该次
请求对应。此接口不是 AXI/APB 自带封装，不应直接接到不匹配的总线上。

|偏移|寄存器|语义|
|---|---|---|
|0x00|CONTROL|bit0 START；bit1 ACK_DONE|
|0x04|STATUS|bit0 BUSY；bit1 sticky DONE；bit2 ERROR|
|0x08|M|1..125|
|0x0c/10/14/18|A/W/P/Y_BASE|32 位字节地址，4B 对齐且区域不重叠|
|0x1c|MODE|0 阻塞；1 有限缓冲重叠|
|0x20/24/28|周期/存储等待/宏忙碌|任务计数，重叠阶段不能相加为总周期|

合法 START 锁存整个任务，DONE 保持到 ACK 或下一合法 START。BUSY 期间
写配置只影响下一任务；重复 START 拒绝并置 ERROR，原任务继续。
ERROR 应作为软件错误返回处理。参数检查失败可能已经读取部分运行时
参数，但不应作为成功任务读取输出。应用程序应先调用 `cim_validate`。

驱动检查 M、模式、对齐、32 位地址空间溢出、四区域互不重叠，以及
逐通道 shift∈[-31,0]、非负 multiplier 与任何合法 U8 输入下的累加器
范围。硬件实际检查范围以 RTL/STATUS 为准。`cim_submit` 仅校验地址配置，
调用者必须先验证已加载的权重/参数。单软件提交者拥有任务及对应 SRAM，
BUSY 期间不修改本任务 SRAM。输入为原始 INT8 字节，bias 不加零点修正。

`cim_pack_weights` 映射 `packed[512*t+8*i+j]=W[8*t+j][i]`。
`cim_pack_params` 显式生成小端字节，不依赖宿主 CPU 大小端。
`cim_device` 要求平台提供 MMIO 访问与 prepare/acquire 回调；RISC-V 平台
可使用有内存 clobber 的 `fence iorw,iorw` 实现顺序，非一致缓存系统还需
已有 BSP 的 clean/invalidate。单独的 fence 不保证脏缓存已写回。

本地 32 位共享存储端口每拍最多一个请求；读最多一个未决响应，无
response-ready。写 ready 必须表示存储已提交。若总线在握手后仍有写
响应，适配器必须等真正提交后再向核返回 ready，避免 DONE 早于可见写回。
复位是任务终止，不是暂停恢复；外部适配器同步丢弃/排空旧读响应后才能
启动下一任务，禁止旧响应进入新任务。

`sw/example.c` 是通用裸机调用示例，由目标 BSP 提供 MMIO 和 SRAM 映射。
K7 的实际适配位于 `sw/k7_main.c` 和 `fpga/cim_rv_system.sv`，固件调用
同一 `cim_submit` 驱动，已通过 RV32I SoC 仿真和板测。移植到其他 SoC
时，由该平台实现地址映射及缓存可见性约定。

## 当前可执行入口

```
python tools/synth.py --driver
python tools/synth.py
python tools/synth.py --generic
```

第一条编译驱动/例子并运行宿主参数与打包检查；第二条用已发现的 Vivado
执行 HDL analysis；第三条执行与器件无关的 Yosys 综合及结构检查。日志在
`build/checks/`。没有 part 时不会悄悄选择器件。通用综合依赖可安装在项目内：

```
python -m pip install --target build/python_deps yowasp-yosys==0.70.0.0.post1259 yowasp-runtime==1.96 wasmtime==47.0.1
```

已实际使用 [YoWASP Yosys](https://github.com/YoWASP/yosys)
0.70.0.0.post1259（Yosys 0.70，git 28ba3cb92，ISC），
[YoWASP runtime](https://github.com/YoWASP/runtime-py) 1.96（ISC），以及
[Wasmtime Python](https://github.com/bytecodealliance/wasmtime-py)
47.0.1（Apache-2.0 WITH LLVM-exception）。它们是构建工具，未复制第三方宏 RTL。

`generic_stat.json` 保留各层次计数；`generic_netlist.json` 为已综合网络。
`synth -noabc` 不做 FPGA LUT/DSP 映射，不生成物理面积或时钟结论。
综合可以发现不可综合结构、残余过程和连接问题；时序关键路径、FF/LUT/DSP
占用、布局布线仍须真实器件及约束。宏的并行权重读需要寄存器/分布式存储，
不能因为原始容量4096bit就宣称仅用一个BRAM。

目标器件确认后才运行：

```
python tools/synth.py --part <真实完整型号> --period <实际主时钟周期ns>
vivado -mode batch -source fpga/implement.tcl -tclargs <part> <board_top> <wrapper.sv> <board.xdc>
```

`synth.tcl` 仅做核的 out-of-context 综合，输出分层资源和综合时序报告，
不是板级时序签核；`implement.tcl` 要求真实板级 wrapper/XDC，输出 setup、
hold、约束检查、DRC 和布线结果。缺少 IO timing、未约束路径或未经论证的
例外应在签核前解决，不能仅凭 bitstream 生成成功宣称时序通过。

现有 K7 V2.1 接入复用了本机 JYDD RISC-V CPU。内存映射、固件构建与
板测入口见 [BOARD_K7.md](BOARD_K7.md)，实测状态见 [STATUS.md](STATUS.md)。
