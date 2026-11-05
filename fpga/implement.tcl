# Usage: vivado -mode batch -source fpga/implement.tcl -tclargs
#        PART BOARD_TOP BOARD_WRAPPER BOARD_XDC
# The board XDC must constrain clk, IO timing and every physical pin in the
# actual wrapper. No generated clocks or global false paths are added here.
if {$argc != 4} { error "Provide confirmed PART TOP WRAPPER XDC; no defaults" }
set part [lindex $argv 0]
set top [lindex $argv 1]
set wrapper [file normalize [lindex $argv 2]]
set xdc [file normalize [lindex $argv 3]]
foreach path [list $wrapper $xdc] {
    if {![file isfile $path]} { error "Missing input: $path" }
}
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build fpga]
file mkdir $out
create_project -in_memory -part $part
read_verilog -sv [glob [file join $root rtl *.sv]]
read_verilog -sv $wrapper
read_xdc $xdc
synth_design -top $top -part $part
if {[llength [get_clocks]] == 0} { error "XDC defines no clocks" }
opt_design
place_design
phys_opt_design
route_design
report_utilization -hierarchical -file [file join $out utilization.rpt]
report_timing_summary -report_unconstrained -file [file join $out timing.rpt]
report_methodology -file [file join $out methodology.rpt]
report_drc -file [file join $out drc.rpt]
check_timing -verbose -file [file join $out check_timing.rpt]
write_checkpoint -force [file join $out routed.dcp]
set setup_path [get_timing_paths -delay_type max -max_paths 1]
set hold_path [get_timing_paths -delay_type min -max_paths 1]
if {[llength $setup_path] == 0 || [llength $hold_path] == 0} {
    error "No setup/hold timing paths: inspect clock and constraints"
}
if {[get_property SLACK $setup_path] < 0 || [get_property SLACK $hold_path] < 0} {
    error "Timing failed; inspect build/fpga/timing.rpt"
}
# Bitstream is deliberately generated only after the reports above. Vivado DRC
# enforces pin/electrical rules. check_timing still requires human review for
# missing IO delays and justified asynchronous paths before calling signoff.
write_bitstream -force [file join $out cim_board.bit]
puts "Implementation completed; review check_timing, DRC and constraint coverage before signoff"
