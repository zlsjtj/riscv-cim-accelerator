# Invoke from the output directory with the firmware, SRAM and staged CPU include.
if {$argc != 4} {error "Usage: build_k7.tcl LOCAL_CPU_SOURCE_ROOT TURNAROUND INPUT_CACHE USR_ACCESS"}
lassign $argv cpu turn cache usr_access
set cpu [file normalize $cpu]
set root [file normalize [file join [file dirname [info script]] ..]]
set part xc7k325tffg900-2
set_param general.maxThreads 4
create_project -in_memory -part $part
if {![file isfile cpu_include/myCPU_m_ext.sv]} {error "Run k7.py prepare first"}
set_property include_dirs [list [file normalize cpu_include] [file join $cpu common]] [current_fileset]
foreach name {RF Control IMMGEN CCTL ALU ACTL CSR} {
    read_verilog -sv [file join $cpu common $name.sv]
}
foreach name {myCPU uart} {
    read_verilog -sv [file join $cpu route_src $name.sv]
}
read_verilog -sv [glob [file join $root rtl *.sv]]
read_verilog -sv [list [file join $root fpga cim_rv_system.sv] [file join $root fpga cim_k7_top.sv]]
read_xdc [file join $root fpga cim_k7.xdc]
synth_design -top cim_k7_top -part $part -generic [list TURNAROUND=$turn INPUT_CACHE=$cache]
report_clocks -file clocks.rpt
report_utilization -hierarchical -file synth_utilization.rpt
report_timing_summary -file synth_timing.rpt
write_checkpoint -force synthesized.dcp
opt_design
place_design
phys_opt_design
route_design
report_route_status -file route.rpt
report_utilization -hierarchical -file utilization.rpt
report_timing_summary -delay_type min_max -report_unconstrained -file timing.rpt
report_timing -delay_type max -max_paths 8 -file critical_paths.rpt
report_drc -file drc.rpt
check_timing -verbose -file check_timing.rpt
write_checkpoint -force routed.dcp
set setup [get_timing_paths -delay_type max -max_paths 1]
set hold [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup] != 1 || [llength $hold] != 1} {error "Missing timed setup or hold path"}
set wns [get_property SLACK $setup]
set whs [get_property SLACK $hold]
puts "K7_WNS_NS=$wns K7_WHS_NS=$whs"
if {$wns < 0 || $whs < 0} {error "K7 timing failed"}
if {[llength [get_drc_violations -filter {SEVERITY == Error}]]} {error "K7 DRC errors"}
set drc_file [open drc.rpt r]
set drc_text [read $drc_file]
close $drc_file
if {[regexp -line {^REQP-1839#} $drc_text]} {error "Asynchronous BRAM control warning remains"}
set spad_brams [llength [get_cells -quiet -hier -filter {REF_NAME == RAMB36E1 && NAME =~ *input_spad*}]]
set next_addr_ffs [llength [get_cells -quiet -hier -filter {REF_NAME =~ FD* && NAME =~ *rd_next_addr_reg*}]]
puts "K7_STRUCTURES SPAD_RAMB36=$spad_brams NEXT_ADDR_FFS=$next_addr_ffs"
if {$spad_brams != 2*($cache != 0) || ($next_addr_ffs > 0) != $turn} {error "Variant structures disagree with the configuration"}
set retained_brams [llength [get_cells -quiet -hier -filter {REF_NAME == RAMB36E1 && NAME =~ *interlayer_ram*}]]
puts "K7_INTERLAYER_RAMB36=$retained_brams"
if {$retained_brams != 2*($cache == 3)} {error "Unexpected interlayer BRAM inference"}
set_property BITSTREAM.CONFIG.USERID 0x$usr_access [current_design]
set_property BITSTREAM.CONFIG.USR_ACCESS 0x$usr_access [current_design]
write_bitstream -force cim_k7.bit
puts "K7_BITSTREAM_READY"
