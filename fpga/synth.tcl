# Usage: vivado -mode batch -source fpga/synth.tcl -tclargs PART PERIOD_NS
# Out-of-context synthesis only: no board pins or board model are assumed.
if {$argc != 2} { error "Provide the CONFIRMED FPGA part and clock period (ns)" }
set part [lindex $argv 0]
set period [lindex $argv 1]
if {![string is double -strict $period] || $period <= 0} { error "Invalid period" }
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build synth]
file mkdir $out
create_project -in_memory -part $part
read_verilog -sv [glob [file join $root rtl *.sv]]
# Supply the confirmed clock before synthesis so timing optimization sees it.
set clock_xdc [file join $out core_clock.xdc]
set clock_file [open $clock_xdc w]
puts $clock_file "create_clock -name core_clk -period $period \[get_ports clk\]"
close $clock_file
read_xdc $clock_xdc
synth_design -top cim_accel -part $part -mode out_of_context
report_utilization -hierarchical -file [file join $out utilization.rpt]
report_timing_summary -report_unconstrained -file [file join $out timing_synth.rpt]
report_methodology -file [file join $out methodology.rpt]
write_checkpoint -force [file join $out cim_accel_synth.dcp]
puts "PASS OOC SYNTHESIS ONLY; no board implementation or physical CiM claim"
