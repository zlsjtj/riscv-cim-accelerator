`timescale 1ns/1ps
module tb_rv_system #(parameter bit TURNAROUND=1, parameter int INPUT_CACHE=0);
    logic clk = 1'b0, rst_n = 1'b0;
    always #10 clk = ~clk;
    wire tx_start;
    wire [7:0] tx_data;
    logic [2:0] busy_cycles = '0;
    string line = "";
    int reset_count = 0;
    logic was_reset = 1'b0;
    int software_runs, software_output_words, last_software_commit;
    int shared_reads, shared_writes, local_reads, local_writes, traffic_file;
    logic was_done;
    cim_rv_system #(.TURNAROUND(TURNAROUND), .INPUT_CACHE(INPUT_CACHE)) dut (
        .clk(clk), .rst_n(rst_n), .tx_busy(busy_cycles != 0),
        .tx_start(tx_start), .tx_data(tx_data)
    );

    logic counter_test;
    logic [31:0] test_addr, test_data;
    logic test_wen;
    task write_test_cfg(input [7:0] addr, input [31:0] data);
        @(negedge clk);
        test_addr=32'h80201000 | {24'b0,addr}; test_data=data; test_wen=1;
        @(negedge clk); test_wen=0;
    endtask

    task test_start_counter;
        logic [31:0] prior;
        force dut.cpu_addr=test_addr;
        force dut.cpu_wdata=test_data;
        force dut.cpu_mask=2'b10;
        force dut.cpu_wen=test_wen;
        write_test_cfg('h08,1);
        write_test_cfg('h0c,'h8010a000);
        write_test_cfg('h10,'h8010c000);
        write_test_cfg('h14,'h8010d000);
        write_test_cfg('h18,'h80108000);
        write_test_cfg('h00,1);
        wait(dut.committed_writes!=0);
        // Reject a START while busy. Account for any write committed that edge.
        @(negedge clk);
        test_addr='h80201000; test_data=1; test_wen=1;
        @(posedge clk);
        if (dut.start_accepted || !dut.accel.busy) $fatal(1,"Busy rejection not exercised");
        prior=dut.committed_writes + (dut.cim_access && dut.mem_write);
        #1;
        if (dut.committed_writes!==prior) $fatal(1,"Busy rejection changed committed_writes");
        @(negedge clk); test_wen=0;
        wait(dut.accel.done);
        if (dut.committed_writes!=16) $fatal(1,"Lost original task writes");
        write_test_cfg('h08,0);
        write_test_cfg('h00,1);
        if (dut.committed_writes!=16 || dut.accel.busy || !dut.accel.error)
            $fatal(1,"Illegal configuration discarded write history");
        write_test_cfg('h08,1);
        write_test_cfg('h00,1);
        if (dut.committed_writes!=0 || !dut.accel.busy)
            $fatal(1,"Accepted START did not clear write history");
        $display("PASS accepted START clears commit counter, rejected START preserves it");
        $finish;
    endtask

    // Optional task-relative trace. Each row samples signals at the named edge
    // before nonblocking assignments, except DONE which is first observed one edge later.
    int trace_file;
    logic trace_done = 1'b0;
    logic trace_ch7 = 1'b0, trace_ctx;
    int profile_file = 0, profile_task = 0;
    initial if ($test$plusargs("PROFILE_TASKS")) begin
        profile_file = $fopen("task_edges.csv", "w");
        if (!profile_file) $fatal(1, "Cannot open task_edges.csv");
        $fdisplay(profile_file, "task,event,mode,M,cycle,tile,state,macro_start,macro_busy,input_wait,raw_full,contexts_full,quant_issue,quant_result,write_pending,write_commit,shared_stall,response_wait,replay");
    end
    always @(posedge clk) if (profile_file) begin
        if (dut.start_accepted) profile_task++;
        if (dut.accel.busy || (dut.accel.done && !was_done))
            $fdisplay(profile_file, "%0d,%s,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
                      profile_task, dut.warm_reset ? "abort" : dut.accel.done ? "done" : "edge",
                      dut.accel.mode, dut.accel.task_m, dut.accel.cycles + (dut.accel.busy ? 1 : 0),
                      dut.accel.tile, dut.accel.state, dut.accel.mac_start, dut.accel.mac_busy,
                      |(dut.accel.live & ~dut.accel.input_ready),
                      &(dut.accel.raw_valid | dut.accel.raw_reserved), &dut.accel.live,
                      dut.accel.q_valid, dut.accel.q_result_valid, |dut.accel.output_ready,
                      dut.cim_access && dut.mem_write, dut.mem_valid && !dut.mem_ready,
                      dut.accel.rd_pending && !dut.mem_rvalid, dut.accel.spad_read);
    end
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
        was_done <= dut.accel.done;
        if (!dut.run_n || dut.start_accepted) begin
            shared_reads=0; shared_writes=0; local_reads=0; local_writes=0;
        end else begin
            if (dut.cim_access && !dut.mem_write) shared_reads++;
            if (dut.cim_access && dut.mem_write) shared_writes++;
            if (dut.accel.spad_read) local_reads += INPUT_CACHE==2 ? 2 : 1;
            if (dut.accel.spad_write) local_writes++;
            if (traffic_file && dut.accel.done && !was_done)
                $fdisplay(traffic_file, "%0d,%0d,%0d,%0d,%0d,%0d,%0d", dut.accel.mode,
                          dut.accel.task_m, dut.accel.cycles, shared_reads, shared_writes, local_reads, local_writes);
        end
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
                    if (software_runs != 2) $fatal(1, "Expected two complete software timer windows");
                    $fclose(traffic_file);
                    if (profile_file) $fclose(profile_file);
                    $finish;
                end
                if (line == "CIM_FAIL") $fatal(1, "RV32I comparison failed");
                line = "";
            end else
                line = {line, tx_data};
        end
    end
    initial begin
        counter_test = $test$plusargs("TEST_START_COUNTER");
        if (!counter_test) begin
            traffic_file = $fopen("traffic.csv", "w");
            if (!traffic_file) $fatal(1, "Cannot open traffic.csv");
            $fdisplay(traffic_file, "mode,M,cycles,shared_reads,shared_writes,cache_reads,cache_writes");
        end
        test_addr=0; test_data=0; test_wen=0;
        repeat (8) @(negedge clk);
        rst_n = 1'b1;
        if (counter_test) fork
            test_start_counter();
            begin repeat (20000) @(posedge clk); $fatal(1, "Commit counter test timed out"); end
        join
        repeat (4000000) @(posedge clk);
        $fatal(1, "RV32I firmware timed out");
    end
endmodule
