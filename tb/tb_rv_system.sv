`timescale 1ns/1ps
module tb_rv_system;
    logic clk = 1'b0, rst_n = 1'b0;
    always #10 clk = ~clk;
    wire tx_start;
    wire [7:0] tx_data;
    logic [2:0] busy_cycles = '0;
    string line = "";
    int reset_count = 0;
`ifdef CIM_SW_TIMER
    int software_runs = 0, software_output_words = 0, last_software_commit = 0;
`endif
    logic was_reset = 1'b0;
    cim_rv_system dut (
        .clk(clk), .rst_n(rst_n), .tx_busy(busy_cycles != 0),
        .tx_start(tx_start), .tx_data(tx_data)
    );

    // Optional task-relative trace. Each row samples signals at the named edge
    // before nonblocking assignments, except DONE which is first observed one edge later.
    int trace_file;
    int memory_file;
    int reads[3], write_beats, port_stalls, pending_cycles, delayed_cycles;
    int run_cycles, live_one, live_two, macro_starts, macro_busy, macro_input_wait;
    int quant_issue, quant_retire, quant_contention, write_ready, write_wait;
    logic trace_done = 1'b0;
    logic trace_ch7 = 1'b0, trace_ctx;
    initial if ($test$plusargs("TRACE_BLOCKS")) begin
        trace_file = $fopen("block_trace.csv", "w");
        if (!trace_file) $fatal(1, "Cannot open block_trace.csv");
        $fdisplay(trace_file, "event,mode,M,cycle,tile,position,context,time_ns,rd_pending,mem_valid,mem_write,mem_ready,output_ready");
        memory_file = $fopen("memory_profile.csv", "w");
        if (!memory_file) $fatal(1, "Cannot open memory_profile.csv");
        $fdisplay(memory_file, "mode,M,cycles,param_reads,weight_reads,input_reads,writes,port_stalls,rd_pending,rd_wait_after_accept,run_cycles,live_one,live_two,macro_starts,macro_busy,macro_input_wait,quant_issue,quant_retire,quant_contention,write_ready,write_wait");
    end
    always @(posedge clk) if (memory_file) begin
        if (dut.run_n && dut.accel.done && !trace_done)
            $fdisplay(memory_file, "%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
                      dut.accel.mode, dut.accel.task_m, dut.accel.cycles, reads[0], reads[1], reads[2],
                      write_beats, port_stalls, pending_cycles, delayed_cycles, run_cycles, live_one,
                      live_two, macro_starts, macro_busy, macro_input_wait, quant_issue, quant_retire, quant_contention,
                      write_ready, write_wait);
        if (!dut.run_n || !dut.accel.busy) begin
            foreach (reads[i]) reads[i] = 0;
            write_beats=0; port_stalls=0; pending_cycles=0; delayed_cycles=0;
            run_cycles=0; live_one=0; live_two=0; macro_starts=0; macro_busy=0;
            macro_input_wait=0; quant_issue=0; quant_retire=0; quant_contention=0;
            write_ready=0; write_wait=0;
        end else begin
            if (dut.cim_access && !dut.mem_write) reads[dut.accel.req_kind]++;
            if (dut.cim_access && dut.mem_write) write_beats++;
            if (dut.mem_valid && !dut.mem_ready) port_stalls++;
            if (dut.accel.rd_pending) pending_cycles++;
            if (dut.accel.rd_pending && !dut.mem_rvalid) delayed_cycles++;
            if (dut.accel.state == dut.accel.RUN) begin
                run_cycles++;
                if (^dut.accel.live) live_one++;
                if (&dut.accel.live) live_two++;
                if (dut.accel.mac_start) macro_starts++;
                if (dut.accel.mac_busy) macro_busy++;
                if (dut.accel.mac_ready && !dut.accel.mac_start &&
                    !(&(dut.accel.raw_valid | dut.accel.raw_reserved)) &&
                    |(dut.accel.live & ~dut.accel.input_ready)) macro_input_wait++;
                if (dut.accel.q_valid) quant_issue++;
                if (dut.accel.q_result_valid) quant_retire++;
                if (&(dut.accel.live & dut.accel.recon_done) &&
                    !dut.accel.quant_index[0][3] && !dut.accel.quant_index[1][3]) quant_contention++;
                if (|dut.accel.output_ready) begin
                    write_ready++;
                    if (dut.accel.rd_pending || (dut.mem_valid && !dut.mem_write)) write_wait++;
                end
            end
        end
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
`ifdef CIM_SW_TIMER
        if (dut.sw_active && dut.cpu_store && dut.cpu_store_word >= 14'h2000 &&
            dut.cpu_store_word < 14'h27d0) begin
            software_output_words++;
            last_software_commit = dut.sw_cycles+1;
        end
        if (dut.run_n && dut.cpu_wen && dut.cpu_mask == 2'b10 && dut.cpu_addr == dut.SW_TIMER) begin
            if (dut.cpu_wdata[0]) begin
                software_output_words=0;
                last_software_commit=0;
            end else begin
                if (!dut.sw_active || software_output_words != (software_runs==0 ? 16 : 2000))
                    $fatal(1, "Software timer stopped before all SRAM output commits");
                software_runs++;
                $display("CPU_TIMER last_commit_to_stop_cycles=%0d words=%0d",
                         dut.sw_cycles+1-last_software_commit, software_output_words);
            end
        end
`endif
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
`ifdef CIM_SW_TIMER
                    if (software_runs != 2) $fatal(1, "Expected two complete software timer windows");
`endif
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
        repeat (20000000) @(posedge clk);
        $fatal(1, "RV32I firmware timed out");
    end
endmodule
