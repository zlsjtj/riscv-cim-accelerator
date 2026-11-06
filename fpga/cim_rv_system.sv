`timescale 1ns/1ps
// Adapter for the existing JYDD myCPU registered peripheral interface.
module cim_rv_system #(
    parameter ROM_FILE = "firmware.mem",
    parameter RAM_FILE = "sram.mem",
    parameter bit TURNAROUND=1,
    parameter int INPUT_CACHE=0
) (
    input logic clk, rst_n,
    input logic tx_busy,
    output logic tx_start,
    output logic [7:0] tx_data
);
    localparam logic [31:0] CIM_BASE = 32'h80201000;
    localparam logic [31:0] UART_STATUS = 32'h80201100;
    localparam logic [31:0] UART_DATA = 32'h80201104;
    localparam logic [31:0] WRITE_COUNT = 32'h80201108;
    localparam logic [31:0] RESET_CONTROL = 32'h8020110c;
    localparam logic [31:0] RESET_STATUS = 32'h80201110;
    localparam logic [31:0] RESET_WRITES = 32'h80201114;
    localparam logic [31:0] SW_TIMER = 32'h80201118;

    logic reset_armed, warm_reset;
    logic [1:0] reset_epoch;
    logic [3:0] interrupted_status;
    logic [31:0] interrupted_writes;
    wire run_n = rst_n && !warm_reset;

    logic [31:0] rom [0:4095];
    (* ram_style = "block" *) logic [31:0] sram [0:16383];
    initial begin
        $readmemh(ROM_FILE, rom);
        $readmemh(RAM_FILE, sram);
    end

    wire [11:0] insn_word;
    wire [15:0] cpu_read_word;
    wire [31:0] cpu_addr, cpu_wdata;
    logic [31:0] cpu_rdata, cpu_mmio_rdata;
    wire cpu_wen;
    wire [1:0] cpu_mask;
    myCPU #(
        .ENABLE_XPERM4(1'b0), .EARLY_REGISTERED_LOAD_REQUEST(1'b0),
        .LOAD_FILL_STORE_CACHE(1'b0), .FAST_LOAD_STORE_FORWARD(1'b0)
    ) cpu (
        .cpu_rst(!run_n), .cpu_clk(clk),
        .irom_addr(), .irom_word_addr(insn_word), .irom_data(rom[insn_word]),
        .perip_addr(cpu_addr), .dram_word_addr(cpu_read_word),
        .perip_wen(cpu_wen), .perip_mask(cpu_mask), .perip_wdata(cpu_wdata),
        .dram_rdata(cpu_rdata), .mmio_rdata(cpu_mmio_rdata),
        .profile_enable(1'b0), .profile_sel(4'd0), .profile_data()
    );

    wire cim_select = cpu_addr[31:8] == CIM_BASE[31:8];
    wire cfg_write = cpu_wen && cim_select && cpu_mask == 2'b10;
    // Sample actual CiM STATUS on the diagnostic bus while the CPU waits.
    wire [7:0] cfg_addr = cim_select ? cpu_addr[7:0] : 8'h04;
    wire [31:0] cfg_rdata;
    wire start_accepted;
    wire mem_valid, mem_write, mem_ready;
    wire [31:0] mem_addr, mem_wdata;
    wire [3:0] mem_wstrb;
    logic mem_rvalid;
    logic [31:0] port_b_rdata;
    logic [31:0] committed_writes;
    logic sw_active;
    logic [31:0] sw_cycles;

    cim_accel #(.TURNAROUND(TURNAROUND), .INPUT_CACHE(INPUT_CACHE)) accel (
        .clk(clk), .rst_n(run_n), .cfg_valid(cim_select),
        .cfg_write(cfg_write), .cfg_addr(cfg_addr), .cfg_wdata(cpu_wdata),
        .cfg_ready(), .cfg_rdata(cfg_rdata), .start_accepted(start_accepted),
        .mem_valid(mem_valid), .mem_write(mem_write), .mem_addr(mem_addr),
        .mem_wdata(mem_wdata), .mem_wstrb(mem_wstrb), .mem_ready(mem_ready),
        .mem_rvalid(mem_rvalid), .mem_rdata(port_b_rdata)
    );

    // Match the existing bridge's one-cycle CPU write staging. Port A is a
    // synchronous CPU read. Port B grants a pending CPU store first, then CIM.
    logic cpu_store;
    logic [13:0] cpu_store_word;
    logic [31:0] cpu_store_data;
    logic [3:0] cpu_store_lanes;
    wire cim_in_sram = mem_addr[31:16] == 16'h8010 && mem_addr[1:0] == 2'b00;
    assign mem_ready = run_n && !cpu_store && cim_in_sram;
    wire cim_access = mem_valid && mem_ready;
    wire [13:0] b_word = cpu_store ? cpu_store_word : mem_addr[15:2];
    wire [31:0] b_data = cpu_store ? cpu_store_data : mem_wdata;
    wire [3:0] b_lanes = cpu_store ? cpu_store_lanes : (mem_write ? mem_wstrb : 4'b0000);

    always_ff @(posedge clk) begin
        cpu_rdata <= sram[cpu_read_word[13:0]];
        if (run_n && (cpu_store || cim_access)) begin
            port_b_rdata <= sram[b_word];
            for (int byte_i = 0; byte_i < 4; byte_i++)
                if (b_lanes[byte_i])
                    sram[b_word][byte_i*8 +: 8] <= b_data[byte_i*8 +: 8];
        end
    end

    always_comb begin
        cpu_mmio_rdata = 32'd0;
        if (cim_select)
            cpu_mmio_rdata = cfg_rdata;
        else if (cpu_addr == UART_STATUS)
            cpu_mmio_rdata = {31'd0, tx_busy || tx_start};
        else if (cpu_addr == WRITE_COUNT)
            cpu_mmio_rdata = committed_writes;
        else if (cpu_addr == RESET_CONTROL)
            cpu_mmio_rdata = {30'd0, reset_epoch};
        else if (cpu_addr == RESET_STATUS)
            cpu_mmio_rdata = {28'd0, interrupted_status};
        else if (cpu_addr == RESET_WRITES)
            cpu_mmio_rdata = interrupted_writes;
        else if (cpu_addr == SW_TIMER)
            cpu_mmio_rdata = sw_cycles;
    end

    // Retain the event record across a warm reset. Firmware arms the event
    // after a write has committed. Reset on the next accepted read while busy,
    // so the read response is present at the reset edge and gets discarded.
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            reset_armed <= 1'b0;
            warm_reset <= 1'b0;
            reset_epoch <= '0;
            interrupted_status <= '0;
            interrupted_writes <= '0;
        end else begin
            warm_reset <= 1'b0;
            if (warm_reset)
                interrupted_status[3] <= mem_rvalid;
            if (run_n && cpu_wen && cpu_mask == 2'b10 && cpu_addr == RESET_CONTROL &&
                cpu_wdata == 32'd1 && reset_epoch < 2 && cfg_rdata[2:0] == 3'b001 &&
                committed_writes != 0)
                reset_armed <= 1'b1;
            if (reset_armed && !cim_select && cfg_rdata[2:0] == 3'b001 &&
                cim_access && !mem_write) begin
                reset_armed <= 1'b0;
                warm_reset <= 1'b1;
                reset_epoch <= reset_epoch + 1'b1;
                interrupted_status <= {1'b0, cfg_rdata[2:0]};
                interrupted_writes <= committed_writes;
            end
        end
    end

    always_ff @(posedge clk) begin
        if (!run_n) begin
            cpu_store <= 1'b0;
            mem_rvalid <= 1'b0;
            committed_writes <= '0;
            sw_active <= 1'b0;
            sw_cycles <= '0;
            tx_start <= 1'b0;
            tx_data <= '0;
        end else begin
            if (sw_active)
                sw_cycles <= sw_cycles + 1'b1;
            if (cpu_wen && cpu_mask == 2'b10 && cpu_addr == SW_TIMER) begin
                sw_active <= cpu_wdata[0];
                if (cpu_wdata[0]) sw_cycles <= '0;
            end
            cpu_store <= cpu_wen && cpu_addr[31:16] == 16'h8010;
            if (cpu_wen && cpu_addr[31:16] == 16'h8010) begin
                cpu_store_word <= cpu_addr[15:2];
                case (cpu_mask)
                    2'b00: begin
                        cpu_store_lanes <= 4'b0001 << cpu_addr[1:0];
                        cpu_store_data <= {4{cpu_wdata[7:0]}};
                    end
                    2'b01: begin
                        cpu_store_lanes <= cpu_addr[1] ? 4'b1100 : 4'b0011;
                        cpu_store_data <= {2{cpu_wdata[15:0]}};
                    end
                    default: begin
                        cpu_store_lanes <= 4'b1111;
                        cpu_store_data <= cpu_wdata;
                    end
                endcase
            end
            mem_rvalid <= cim_access && !mem_write;
            if (start_accepted)
                committed_writes <= '0;
            else if (cim_access && mem_write)
                committed_writes <= committed_writes + 1'b1;
            tx_start <= cpu_wen && cpu_addr == UART_DATA && !tx_busy && !tx_start;
            if (cpu_wen && cpu_addr == UART_DATA)
                tx_data <= cpu_wdata[7:0];
        end
    end
endmodule
