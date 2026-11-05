# XC7K325T V2.1 schematic pp. 4/5/12 and local digital_twin_265.xdc.
set_property -dict {PACKAGE_PIN AD12 IOSTANDARD DIFF_HSTL_II_18} [get_ports clk_p]
set_property -dict {PACKAGE_PIN AD11 IOSTANDARD DIFF_HSTL_II_18} [get_ports clk_n]
set_property -dict {PACKAGE_PIN D17 IOSTANDARD LVCMOS33} [get_ports uart_tx]
create_clock -name ref200 -period 5.000 [get_ports clk_p]
# Asynchronous serial line to the independent CP2104 UART receiver.
set_false_path -to [get_ports uart_tx]
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
