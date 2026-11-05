`timescale 1ns/1ps
// Independently implemented digital W4A4 proxy; not third-party macro RTL.
// E0=start accepted; E1..E4 sample A[3]..A[0]. After E4 result_valid
// is high for one cycle, busy is low. Earliest next acceptance is E5.
module cim_macro (
    input  logic clk, rst_n,
    input  logic w_valid,
    output logic w_ready,
    input  logic [5:0] w_row,
    input  logic [63:0] w_data,
    input  logic start,
    output logic start_ready,
    input  logic [63:0] a_plane,
    output logic busy,
    output logic result_valid,
    output logic [223:0] result_data
);
    // 64 physical rows x 64 bits. Parallel column reduction requires
    // registers/distributed memory; this is not a single-ported BRAM model.
    logic [3:0] weights [0:63][0:15];
    logic [1:0] phase;
    logic signed [15:0] accum [0:15];
    // Each level doubles the number of terms. 11 signed bits cover
    // 64*15 = 960 and 64*(-8) = -512, including the unsigned columns.
    logic signed [10:0] plane_tree [0:15][1:127];
    logic signed [15:0] next_accum [0:15];
    integer c;

    assign w_ready = !busy;
    assign start_ready = !busy && !w_valid; // Programming has priority.

    always_comb begin
        for (int col=0; col<16; col++) begin
            for (int row=0; row<64; row++) begin
                if (!a_plane[row])
                    plane_tree[col][64+row] = '0;
                else if ((col % 2) == 0)
                    plane_tree[col][64+row] = $signed({1'b0, weights[row][col]});
                else
                    plane_tree[col][64+row] = $signed(weights[row][col]);
            end
            for (int node=63; node>=1; node--)
                plane_tree[col][node] = plane_tree[col][2*node] + plane_tree[col][2*node+1];
            next_accum[col] = (accum[col] <<< 1) + plane_tree[col][1];
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            busy <= 1'b0;
            result_valid <= 1'b0;
            result_data <= '0;
            phase <= '0;
            for (c=0; c<16; c=c+1) accum[c] <= '0;
            // Weight RAM is intentionally not reset. Every task programs all
            // rows before any operation; reset aborts rather than resumes it.
        end else begin
            result_valid <= 1'b0;
            if (w_valid && w_ready) begin
                for (c=0; c<16; c=c+1)
                    weights[w_row][c] <= w_data[c*4 +: 4];
            end
            if (start && start_ready) begin
                busy <= 1'b1;
                phase <= 2'd0;
                for (c=0; c<16; c=c+1) accum[c] <= '0;
            end else if (busy) begin
                for (c=0; c<16; c=c+1) begin
                    accum[c] <= next_accum[c];
                    if (phase == 2'd3)
                        result_data[c*14 +: 14] <= next_accum[c][13:0];
                end
                if (phase == 2'd3) begin
                    busy <= 1'b0;
                    result_valid <= 1'b1;
                end else phase <= phase + 1'b1;
            end
        end
    end
endmodule
