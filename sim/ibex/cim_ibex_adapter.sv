// SPDX-License-Identifier: Apache-2.0
module cim_ibex_adapter (
    input logic clk, rst_n,
    input logic cfg_req, cfg_we,
    input logic [3:0] cfg_be,
    input logic [9:0] cfg_addr,
    input logic [31:0] cfg_wdata,
    output logic cfg_rvalid, cfg_error,
    output logic [31:0] cfg_rdata,
    input logic cpu_req, cpu_we,
    input logic [3:0] cpu_be,
    input logic [31:0] cpu_addr, cpu_wdata,
    output logic cpu_rvalid,
    output logic ram_req, ram_we,
    output logic [3:0] ram_be,
    output logic [31:0] ram_addr, ram_wdata,
    input logic ram_rvalid,
    input logic [31:0] ram_rdata
);
    logic mem_valid, mem_write, mem_ready, start_accepted;
    logic [31:0] mem_addr, mem_wdata, cfg_value;
    logic [3:0] mem_wstrb;
    logic cpu_response, cim_read_response;
    int unsigned starts, reads, writes, completions;
    logic previous_done;

    wire cfg_access = cfg_req && cfg_addr[1:0] == 0 && cfg_addr[9:8] == 0 &&
                      (!cfg_we || cfg_be == 4'hf);
    wire address_in_ram = mem_addr[31:20] == 12'h001 && mem_addr[1:0] == 0;
    wire cim_accept = mem_valid && mem_ready;

    // The Simple System bus expects a response on the next edge. CPU RAM
    // requests therefore take precedence. One response tag follows port A.
    assign mem_ready = rst_n && !cpu_req && address_in_ram;
    assign ram_req = cpu_req || cim_accept;
    assign ram_we = cpu_req ? cpu_we : mem_write;
    assign ram_be = cpu_req ? cpu_be : mem_wstrb;
    assign ram_addr = cpu_req ? cpu_addr : mem_addr;
    assign ram_wdata = cpu_req ? cpu_wdata : mem_wdata;
    assign cpu_rvalid = ram_rvalid && cpu_response;

    cim_accel #(.TURNAROUND(1), .INPUT_CACHE(5)) accel (
        .clk, .rst_n, .cfg_valid(cfg_access), .cfg_write(cfg_we),
        .cfg_addr(cfg_addr[7:0]), .cfg_wdata, .cfg_rdata(cfg_value), .start_accepted,
        .mem_valid, .mem_write, .mem_addr, .mem_wdata, .mem_wstrb, .mem_ready,
        .mem_rvalid(ram_rvalid && cim_read_response), .mem_rdata(ram_rdata)
    );

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            cfg_rvalid <= 0;
            cfg_error <= 0;
            cfg_rdata <= 0;
            cpu_response <= 0;
            cim_read_response <= 0;
            starts <= 0;
            reads <= 0;
            writes <= 0;
            completions <= 0;
            previous_done <= 0;
        end else begin
            cfg_rvalid <= cfg_req;
            cfg_error <= cfg_req && !cfg_access;
            if (cfg_req) cfg_rdata <= cfg_value;
            cpu_response <= cpu_req;
            cim_read_response <= cim_accept && !mem_write;
            if (start_accepted) starts <= starts + 1;
            if (cim_accept && !mem_write) reads <= reads + 1;
            if (cim_accept && mem_write) writes <= writes + 1;
            if (accel.done && !previous_done) completions <= completions + 1;
            previous_done <= accel.done;
            if (mem_valid && !address_in_ram) $fatal(1, "CiM request outside Simple System SRAM");
        end
    end

    final $display("CIM_HW %0d %0d %0d %0d", starts, completions, reads, writes);
endmodule
