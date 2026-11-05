# Read-only cable and FPGA discovery.
open_hw_manager
connect_hw_server -url localhost:3121
foreach target [get_hw_targets] {
    puts "JTAG_TARGET=$target"
    current_hw_target $target
    open_hw_target
    foreach dev [get_hw_devices] {
        puts "JTAG_DEVICE=$dev PART=[get_property PART $dev]"
        refresh_hw_device -update_hw_probes false $dev
        foreach prop {REGISTER.IR.BIT5_DONE REGISTER.USERCODE REGISTER.USR_ACCESS} {
            if {![catch {get_property $prop $dev} value] && $value ne ""} {
                puts "$prop=$value"
            }
        }
    }
    close_hw_target
}
disconnect_hw_server
close_hw_manager
