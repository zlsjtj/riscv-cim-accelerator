`timescale 1ns/1ps
module tb_units;
    logic clk=0;
    always #5 clk=~clk;
    logic rst_n=0, w_valid=0, w_ready, start=0, start_ready, busy, result_valid;
    logic [5:0] w_row=0;
    logic [63:0] w_data=0, a_plane=0;
    logic [223:0] result_data;
    cim_macro dut(.*);
    logic signed [31:0] acc=0, multiplier=0, shift=0;
    logic enable=0;
    logic [7:0] value;
    requant quant(.*);

    task automatic qcheck(input integer a, m, s, expected_high, expected_rounded,
                           input logic [7:0] expected_value);
        @(negedge clk);
        acc=a; multiplier=m; shift=s; enable=1;
        @(posedge clk); #1;
        if (quant.high !== expected_high || quant.rounded !== $signed(expected_rounded)
                || value !== expected_value)
            $fatal(1,"requant a=%0d m=%0d s=%0d high=%0d rounded=%0d value=%h expected=%0d,%0d,%h",
                   a,m,s,quant.high,quant.rounded,value,expected_high,expected_rounded,expected_value);
    endtask

    task automatic operation(input logic [63:0] planes[0:3], input integer lo, hi);
        @(negedge clk); start=1;
        @(posedge clk); #1;
        if (!busy || result_valid) $fatal(1,"start timing");
        @(negedge clk); start=0;
        for (int b=0; b<4; b++) begin
            a_plane=planes[b];
            // Busy programming must never be accepted.
            w_valid=1; w_data='0;
            #1;
            if (w_ready) $fatal(1,"weight write accepted while busy");
            @(posedge clk); #1;
            if (b<3 && (!busy || result_valid)) $fatal(1,"early result");
            if (b==3) begin
                if (busy || !result_valid) $fatal(1,"late result");
                for (int j=0; j<8; j++) begin
                    if (result_data[28*j +: 14] !== (lo & 14'h3fff)
                      || result_data[28*j+14 +: 14] !== (hi & 14'h3fff))
                        $fatal(1,"macro pair=%0d lo=%0d hi=%0d expected=%0d,%0d",j,
                         result_data[28*j +:14],$signed(result_data[28*j+14 +:14]),lo,hi);
                end
            end
            @(negedge clk);
        end
        w_valid=0;
        @(posedge clk); #1;
        if (result_valid || busy) $fatal(1,"result must be one cycle");
    endtask

    logic [63:0] planes [0:3];
    initial begin
        repeat(2) @(posedge clk);
        @(negedge clk); rst_n=1;
        // W=-113=8'h8f -> U4=15, S4=-8. A=15 gives U14=14400
        // (bit13 set) and S14=-7680, exposing incorrect sign extension.
        for (int i=0; i<64; i++) begin
            @(negedge clk); w_valid=1; w_row=i; w_data=64'h8f8f8f8f8f8f8f8f;
            @(posedge clk); #1;
            if (!w_ready) $fatal(1,"weight programming blocked idle");
        end
        @(negedge clk); w_valid=0;
        for (int i=0; i<4; i++) planes[i]='1;
        operation(planes,14400,-7680);
        planes[0]='1; planes[1]='0; planes[2]='1; planes[3]='0;
        operation(planes,9600,-5120);
        for (int i=0; i<4; i++) planes[i]='0;
        operation(planes,0,0);

        // Achieve the documented minimum II=5: E5 immediately accepts a
        // new start while the previous one-cycle result is consumed.
        @(negedge clk); start=1;
        @(posedge clk); #1;
        @(negedge clk); start=0; a_plane='1;
        repeat (4) begin @(posedge clk); #1; @(negedge clk); end
        if (!result_valid || busy || !start_ready) $fatal(1,"II5 precondition");
        start=1;
        @(posedge clk); #1;
        if (!busy || result_valid) $fatal(1,"II5 acceptance");
        @(negedge clk); start=0; a_plane='0;
        repeat (4) begin @(posedge clk); #1; @(negedge clk); end
        if (!result_valid || busy || result_data !== 224'b0) $fatal(1,"II5 result");

        // Reset aborts a launched operation and prevents a stale completion.
        start=1;
        @(posedge clk); #1;
        @(negedge clk); start=0; rst_n=0;
        @(posedge clk); #1;
        if (busy || result_valid) $fatal(1,"reset abort");
        @(negedge clk); rst_n=1;
        repeat (5) @(posedge clk);
        #1;
        if (busy || result_valid) $fatal(1,"completion after reset");

        // Negative high-multiply uses truncation toward zero after nudge;
        // RoundingDivideByPOT rounds exact negative halves away from zero.
        qcheck(-1,32'sh40000000,0,0,0,8'h80);
        qcheck(-3,32'sh40000000,0,-1,-1,8'h80);
        qcheck(-6,32'sh40000000,-1,-3,-2,8'h80);
        qcheck(6,32'sh40000000,-1,3,2,8'h82);
        qcheck(3,32'sh40000000,0,2,2,8'h82);
        qcheck(1022,32'sh40000000,-1,511,256,8'h7f);
        qcheck(32'sh7fffffff,32'sh7fffffff,-31,2147483646,1,8'h81);
        qcheck(32'sh80000000,32'sh80000000,0,2147483647,2147483647,8'h7f);
        $display("PASS tb_units macro bit planes/U14/S14/timing and requant double-round boundaries");
        $finish;
    end
    initial begin #100000; $fatal(1,"unit timeout"); end
endmodule
