`timescale 1ns/1ps
module tb_rv_system;
    logic clk = 1'b0, rst_n = 1'b0;
    always #10 clk = ~clk;
    wire tx_start;
    wire [7:0] tx_data;
    logic [2:0] busy_cycles = '0;
    string line = "";
    int reset_count = 0;
    logic was_reset = 1'b0;
    cim_rv_system dut (
        .clk(clk), .rst_n(rst_n), .tx_busy(busy_cycles != 0),
        .tx_start(tx_start), .tx_data(tx_data)
    );

    // Optional task-relative trace. Each row samples signals at the named edge
    // before nonblocking assignments, except DONE which is first observed one edge later.
    int trace_file;
    logic trace_done = 1'b0;
    logic trace_ch7 = 1'b0, trace_ctx;
    initial if ($test$plusargs("TRACE_BLOCKS")) begin
        trace_file = $fopen("block_trace.csv", "w");
        if (!trace_file) $fatal(1, "Cannot open block_trace.csv");
        $fdisplay(trace_file, "event,mode,M,cycle,tile,position,context,time_ns,rd_pending,mem_valid,mem_write,mem_ready,output_ready");
    end
    task automatic trace_event(input string name, input int p, input int ctx);
        $fdisplay(trace_file, "%s,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b", name,
                  dut.accel.mode, dut.accel.task_m, dut.accel.cycles + 1, dut.accel.tile,
                  p, ctx, $time, dut.accel.rd_pending, dut.mem_valid, dut.mem_write,
                  dut.mem_ready, dut.accel.output_ready);
    endtask
    always @(posedge clk) if (trace_file) begin
        trace_done <= dut.accel.done;
        trace_ch7 <= 1'b0;
        if (dut.warm_reset)
            trace_event("abort", -1, -1);
        else if (dut.accel.done && !trace_done)
            trace_event("done_seen", -1, -1);
        else if (dut.run_n && dut.accel.state == dut.accel.RUN) begin
            if (dut.accel.next_p < dut.accel.task_m &&
                (dut.accel.live == 0 || (dut.accel.mode && dut.accel.live != 2'b11)))
                trace_event("allocate", dut.accel.next_p, dut.accel.live[0]);
            if (trace_ch7)
                trace_event("after_issue_ch7", dut.accel.position[trace_ctx], trace_ctx);
            if (dut.accel.q_valid && dut.accel.quant_index[dut.accel.q_ctx] == 7) begin
                trace_event("issue_ch7", dut.accel.position[dut.accel.q_ctx], dut.accel.q_ctx);
                trace_ch7 <= 1'b1;
                trace_ctx <= dut.accel.q_ctx;
            end
            if (dut.cim_access && dut.mem_write && dut.accel.req_last)
                trace_event("commit_last", dut.accel.position[dut.accel.req_ctx], dut.accel.req_ctx);
        end
    end
    always @(posedge clk) begin
        was_reset <= dut.warm_reset;
        if (dut.warm_reset) begin
            if (!dut.accel.busy || !dut.accel.rd_pending || !dut.mem_rvalid ||
                dut.run_n || dut.cim_access)
                $fatal(1, "Warm reset did not abort a live read");
            reset_count <= reset_count + 1;
        end
        if (was_reset && (dut.mem_rvalid || dut.accel.rd_pending ||
                          dut.accel.busy || dut.accel.done || dut.committed_writes != 0))
            $fatal(1, "Accelerator state survived warm reset");
        if (busy_cycles != 0)
            busy_cycles <= busy_cycles - 1'b1;
        if (tx_start) begin
            if (busy_cycles != 0) $fatal(1, "CPU UART write lost");
            busy_cycles <= 3;
            if (tx_data == 10) begin
                $display("%s", line);
                if (line == "CIM_PASS") begin
                    if (reset_count != 2) $fatal(1, "Expected two warm resets");
                    $finish;
                end
                if (line == "CIM_FAIL") $fatal(1, "RV32I comparison failed");
                line = "";
            end else
                line = {line, tx_data};
        end
    end
    initial begin
        repeat (8) @(negedge clk);
        rst_n = 1'b1;
        repeat (4000000) @(posedge clk);
        $fatal(1, "RV32I firmware timed out");
    end
endmodule
