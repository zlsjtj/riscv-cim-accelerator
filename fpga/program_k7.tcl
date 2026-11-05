# Volatile configuration of one explicitly selected Digilent target.
if {$argc != 3} {error "Usage: program_k7.tcl JTAG_SERIAL BITSTREAM EXPECTED_USR_ACCESS"}
lassign $argv serial bit expected_id
if {![file isfile $bit]} {error "Missing bitstream $bit"}
open_hw_manager
connect_hw_server -url localhost:3121
set targets {}
foreach target [get_hw_targets] {
    if {[file tail $target] eq $serial} {lappend targets $target}
}
if {[llength $targets] != 1} {error "Expected one JTAG target with serial $serial"}
current_hw_target [lindex $targets 0]
open_hw_target
set devices [get_hw_devices]
if {[llength $devices] != 1} {error "Expected one FPGA on target"}
set dev [lindex $devices 0]
if {[get_property PART $dev] ne "xc7k325t"} {error "Unexpected FPGA device"}
set_property PROGRAM.FILE [file normalize $bit] $dev
program_hw_devices $dev
refresh_hw_device -update_hw_probes false $dev
if {[get_property REGISTER.IR.BIT5_DONE $dev] ne "1"} {error "FPGA DONE did not assert"}
set id [get_property REGISTER.USR_ACCESS $dev]
if {![string equal -nocase $id $expected_id]} {error "Unexpected USR_ACCESS $id"}
puts "K7_PROGRAM_PASS JTAG=$serial USR_ACCESS=$id"
close_hw_target
disconnect_hw_server
close_hw_manager
