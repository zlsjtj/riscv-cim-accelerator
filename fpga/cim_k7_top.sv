`timescale 1ns/1ps
module cim_k7_top #(
    parameter bit TURNAROUND=1,
    parameter bit INPUT_CACHE=0
) (
    input wire clk_p, clk_n,
    output wire uart_tx
);
    wire refclk, feedback, raw_clk, clk, locked;
    IBUFDS ref_buffer (.I(clk_p), .IB(clk_n), .O(refclk));
    MMCME2_BASE #(
        .CLKIN1_PERIOD(5.0), .DIVCLK_DIVIDE(1), .CLKFBOUT_MULT_F(5.0),
        .CLKOUT0_DIVIDE_F(20.0)
    ) clock_50m (
        .CLKIN1(refclk), .CLKFBIN(feedback), .CLKFBOUT(feedback),
        .CLKOUT0(raw_clk), .LOCKED(locked), .RST(1'b0), .PWRDWN(1'b0)
    );
    BUFG core_buffer (.I(raw_clk), .O(clk));
    (* ASYNC_REG = "TRUE" *) logic [3:0] release_reset = '0;
    always_ff @(posedge clk or negedge locked) begin
        if (!locked) release_reset <= '0;
        else release_reset <= {release_reset[2:0], 1'b1};
    end
    // The reset that controls SRAM enable and CPU state changes on clk.
    logic system_run = 1'b0;
    always_ff @(posedge clk)
        system_run <= release_reset[3];

    wire tx_start, tx_busy;
    wire [7:0] tx_data;
    cim_rv_system #(.TURNAROUND(TURNAROUND), .INPUT_CACHE(INPUT_CACHE)) system (
        .clk(clk), .rst_n(system_run), .tx_busy(tx_busy),
        .tx_start(tx_start), .tx_data(tx_data)
    );
    uart #(.CLK_FREQ(50000000), .BAUD_RATE(115200)) board_uart (
        .clk(clk), .rst_n(system_run), .rx(1'b1), .rx_data(), .rx_ready(),
        .tx(uart_tx), .tx_start(tx_start), .tx_data(tx_data), .tx_busy(tx_busy)
    );
endmodule
