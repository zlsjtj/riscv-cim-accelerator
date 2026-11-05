`timescale 1ns/1ps
// TensorFlow v2.16.1 int32 accumulator, TFLITE_SINGLE_ROUNDING=0.
// Contract: shift in [-31,0]. Parent/driver reject out-of-range parameters.
// One shared lane. Capture the product, then round and clamp for the
// controller to collect on the next edge. A new channel can issue every cycle.
module requant (
    input  logic clk, enable,
    input  logic signed [31:0] acc,
    input  logic signed [31:0] multiplier,
    input  logic signed [31:0] shift,
    output logic [7:0] value
);
    logic signed [63:0] product, nudge, nudged, quotient;
    logic signed [31:0] high;
    logic signed [63:0] rounded, offset_value;
    logic [63:0] mask, remainder, threshold;
    logic [5:0] exponent;
    logic saturate_high;

    // Payload is ignored when the controller's registered valid is clear.
    always_ff @(posedge clk) begin
        if (enable) begin
            product <= $signed(acc) * $signed(multiplier);
            exponent <= -shift;
            saturate_high <= acc == 32'sh80000000 && multiplier == 32'sh80000000;
        end
    end

    always_comb begin
        nudge = (product >= 0) ? 64'sd1073741824 : -64'sd1073741823;
        nudged = product + nudge;
        // Signed division truncates toward zero, unlike an arithmetic shift.
        quotient = nudged / 64'sd2147483648;
        if (saturate_high)
            high = 32'sh7fffffff;
        else high = quotient[31:0];
        mask = (64'd1 << exponent) - 64'd1;
        remainder = {{32{high[31]}},high} & mask;
        threshold = (mask >> 1) + ((high < 0) ? 64'd1 : 64'd0);
        rounded = ($signed({{32{high[31]}},high}) >>> exponent)
                    + ((remainder > threshold) ? 64'sd1 : 64'sd0);
        offset_value = rounded - 64'sd128;
        if (offset_value < -64'sd128) value = 8'h80;
        else if (offset_value > 64'sd127) value = 8'h7f;
        else value = offset_value[7:0];
    end
endmodule
