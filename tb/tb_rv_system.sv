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
    logic chain_test, chain_control_test, retain_test, prefetch_test, early_write_test;
    int chain_windows = 0, chain_starts, chain_dones, chain_mid_writes, chain_final_writes;
    int chain_core_cycles, chain_mid_reads, chain_shared_reads, chain_copies;
    int chain_prefetches, chain_early_writes, chain_handoffs;
    logic [2047:0] chain_copied;
    logic chain_final_read;
    wire [31:0] chain_methods = early_write_test ? 6 : prefetch_test ? 5 : retain_test ? 4 : 3;
    wire [31:0] chain_words = chain_windows < chain_methods ? 32'd16 : 32'd2000;
    wire [31:0] chain_method = chain_windows % chain_methods;
    wire [31:0] chain_expected_starts = chain_method == 0 ? 2 : chain_method == 2 ? 0 : 1;
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

    task test_chain_control;
        logic reserved_ctx;
        logic [7:0] old_position, next_position;
        logic [31:0] stalled_addr, stalled_data;
        force dut.cpu_addr=test_addr;
        force dut.cpu_wdata=test_data;
        force dut.cpu_mask=2'b10;
        force dut.cpu_wen=test_wen;
        write_test_cfg('h08,prefetch_test ? 3 : 1);
        write_test_cfg('h1c,1);
        write_test_cfg('h0c,'h80101000);
        write_test_cfg('h10,'h80103000);
        write_test_cfg('h14,'h80105000);
        write_test_cfg('h18,'h80106000);
        write_test_cfg('h2c,'h80104001);
        write_test_cfg('h30,'h80105400);
        write_test_cfg('h34,'h80108000);
        write_test_cfg('h00,5);
        if (dut.accel.busy || !dut.accel.error || dut.committed_writes)
            $fatal(1,"Unaligned second-layer address was accepted");
        write_test_cfg('h2c,'h80104000);
        write_test_cfg('h00,9);
        if (dut.accel.busy || !dut.accel.error) $fatal(1,"RETAIN without CHAIN was accepted");
        if (prefetch_test) begin
            write_test_cfg('h00,21);
            if (dut.accel.busy || !dut.accel.error) $fatal(1,"PREFETCH without RETAIN was accepted");
        end
        if (early_write_test) begin
            write_test_cfg('h00,45);
            if (dut.accel.busy || !dut.accel.error) $fatal(1,"EARLY_WRITE without PREFETCH was accepted");
            write_test_cfg('h1c,0);
            write_test_cfg('h00,61);
            if (dut.accel.busy || !dut.accel.error) $fatal(1,"EARLY_WRITE in MODE0 was accepted");
            write_test_cfg('h1c,1);
        end
        write_test_cfg('h00,early_write_test ? 61 : prefetch_test ? 29 : retain_test ? 13 : 5);
        if (!dut.accel.busy || dut.accel.error) $fatal(1,"Legal chain START failed");
        write_test_cfg('h2c,'h80104004);
        write_test_cfg('h30,'h80105404);
        write_test_cfg('h34,'h80108004);
        if (retain_test) begin
            wait(dut.mem_valid && dut.mem_write);
            @(negedge clk);
            force dut.mem_ready=0;
            repeat (3) begin
                @(posedge clk);
                if (!dut.mem_valid || !dut.mem_write || dut.accel.retain_write)
                    $fatal(1,"Retained copy before SRAM acceptance");
            end
            @(negedge clk);
            release dut.mem_ready;
        end
        wait(dut.accel.a_base == 'h80106000);
        if (dut.accel.w_base != 'h80104000 || dut.accel.p_base != 'h80105400 ||
            dut.accel.y_base != 'h80108000 || dut.committed_writes != (prefetch_test ? 48 : 16) ||
            !dut.accel.busy || dut.accel.done)
            $fatal(1,"Chain handoff consumed shadow configuration or exposed early DONE");
        if (prefetch_test) begin
            wait(dut.accel.spad_rvalid && dut.accel.prefetch_pending);
            reserved_ctx=dut.accel.prefetch_ctx;
            old_position=dut.accel.position[reserved_ctx];
            next_position=dut.accel.next_p;
            @(negedge clk);
            force dut.mem_ready=0;
            repeat (12) begin
                @(posedge clk);
                if (!dut.accel.prefetch_pending || !dut.accel.live[reserved_ctx] ||
                    dut.accel.next_p != next_position || dut.accel.position[reserved_ctx] != old_position)
                    $fatal(1,"Prefetch replaced the old output context under SRAM backpressure");
            end
            if (dut.accel.spad_active || dut.accel.spad_rvalid || !dut.mem_valid || !dut.mem_write)
                $fatal(1,"Expected completed prefetch while old output is stalled");
            if (early_write_test) begin
                if (dut.accel.req_last || dut.accel.req_ctx != reserved_ctx)
                    $fatal(1,"First word lost priority under stall");
                stalled_addr=dut.mem_addr;
                stalled_data=dut.mem_wdata;
                repeat (3) begin
                    @(posedge clk);
                    if (!dut.mem_valid || !dut.mem_write || dut.mem_addr != stalled_addr ||
                        dut.mem_wdata != stalled_data || dut.accel.allocate_row)
                        $fatal(1,"Stalled first word changed");
                end
                @(negedge clk);
                release dut.mem_ready;
                @(posedge clk);
                if (!dut.cim_access || dut.accel.req_last || dut.accel.allocate_row)
                    $fatal(1,"First word commit recycled a live context");
                @(negedge clk);
                force dut.mem_ready=0;
                wait(dut.mem_valid && dut.mem_write);
                repeat (3) begin
                    @(posedge clk);
                    if (!dut.accel.req_last || dut.accel.req_ctx != reserved_ctx ||
                        dut.mem_addr != stalled_addr+4 || dut.accel.allocate_row ||
                        dut.accel.position[reserved_ctx] != old_position)
                        $fatal(1,"Stalled last word lost ownership of the context");
                end
            end
        end else if (retain_test) wait(dut.accel.spad_rvalid && dut.accel.replay_intermediate);
        else wait(dut.mem_rvalid && dut.accel.rd_pending);
        @(negedge clk);
        rst_n = 0;
        if (prefetch_test) release dut.mem_ready;
        @(negedge clk);
        if (dut.accel.busy || dut.accel.done || dut.accel.error ||
            dut.accel.chain_pending || dut.accel.rd_pending || dut.mem_valid || dut.mem_rvalid ||
            dut.accel.retain_intermediate || dut.accel.spad_rvalid ||
            dut.accel.prefetch_pending || dut.committed_writes)
            $fatal(1,"Chain survived reset in layer two");
        $display("PASS chain control alignment, shadow snapshot, commit and reset");
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
        $fdisplay(profile_file, "task,event,mode,M,cycle,tile,state,macro_start,macro_busy,input_wait,raw_full,contexts_full,quant_issue,quant_result,write_pending,write_commit,shared_stall,response_wait,replay,live_mask,input_ready_mask,high_mask,recon_mask,output_ready_mask,allocate,next_p,position0,position1,prefetch_pending,prefetch_ctx,replay_active,replay_result,mac_result,raw_mask,quant_ctx,quant_index,quant_result_ctx,quant_result_channel,write_offer,write_ctx,write_last");
    end
    always @(posedge clk) if (profile_file) begin
        if (dut.start_accepted) profile_task++;
        if (dut.accel.busy || (dut.accel.done && !was_done))
            $fdisplay(profile_file, "%0d,%s,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
                      profile_task, dut.warm_reset ? "abort" : dut.accel.done ? "done" : "edge",
                      dut.accel.mode, dut.accel.task_m, dut.accel.cycles + (dut.accel.busy ? 1 : 0),
                      dut.accel.tile, dut.accel.state, dut.accel.mac_start, dut.accel.mac_busy,
                      |(dut.accel.live & ~dut.accel.input_ready),
                      &(dut.accel.raw_valid | dut.accel.raw_reserved), &dut.accel.live,
                      dut.accel.q_valid, dut.accel.q_result_valid, |dut.accel.output_ready,
                      dut.cim_access && dut.mem_write, dut.mem_valid && !dut.mem_ready,
                      dut.accel.rd_pending && !dut.mem_rvalid, dut.accel.spad_read,
                      dut.accel.live, dut.accel.input_ready, dut.accel.issued_high, dut.accel.recon_done,
                      dut.accel.write_ready, dut.accel.allocate_row, dut.accel.next_p,
                      dut.accel.position[0], dut.accel.position[1], dut.accel.prefetch_pending,
                      dut.accel.prefetch_ctx, dut.accel.spad_active, dut.accel.spad_rvalid,
                      dut.accel.mac_valid, dut.accel.raw_valid,
                      dut.accel.q_ctx, dut.accel.quant_index[dut.accel.q_ctx],
                      dut.accel.q_result_ctx, dut.accel.q_result_channel,
                      dut.mem_valid && dut.mem_write, dut.accel.req_ctx, dut.accel.req_last);
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
            if (dut.accel.allocate_row)
                trace_event("allocate", dut.accel.next_p, dut.accel.allocate_ctx);
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
            if (dut.accel.spad_read) local_reads += INPUT_CACHE>=2 ? 2 : 1;
            if (dut.accel.spad_write) local_writes++;
            if (traffic_file && dut.accel.done && !was_done)
                $fdisplay(traffic_file, "%0d,%0d,%0d,%0d,%0d,%0d,%0d", dut.accel.mode,
                          dut.accel.task_m, dut.accel.cycles, shared_reads, shared_writes, local_reads, local_writes);
        end
        if (chain_test && dut.sw_active) begin
            if (dut.accel.prefetch_start) chain_prefetches++;
            if (dut.accel.prefetch_pending && dut.accel.spad_rvalid &&
                (chain_method < 4 || dut.accel.spad_result_ctx != dut.accel.prefetch_ctx ||
                 (dut.accel.mac_busy && dut.accel.plane_ctx == dut.accel.prefetch_ctx)))
                $fatal(1, "Prefetched data overwrote an input slot still in use");
            if (dut.accel.prefetch_pending && dut.accel.allocate_row) begin
                if (dut.accel.spad_active || dut.accel.spad_rvalid)
                    $fatal(1, "Prefetched row activated before its replay drained");
                if (dut.accel.live[dut.accel.allocate_ctx]) begin
                    if (chain_method != 5 || !dut.cim_access || !dut.mem_write ||
                        !dut.accel.req_last || dut.accel.req_ctx != dut.accel.allocate_ctx)
                        $fatal(1, "Prefetched row activated before the previous output committed");
                    chain_handoffs++;
                end
            end
            if (dut.cim_access && dut.mem_write && !dut.accel.output_ready[dut.accel.req_ctx]) begin
                if (chain_method != 5 || !dut.accel.replay_intermediate || dut.accel.req_last ||
                    !dut.accel.first_word_ready[dut.accel.req_ctx])
                    $fatal(1, "Write committed before its word finished quantization");
                chain_early_writes++;
            end
            if (dut.start_accepted) chain_starts++;
            if (dut.accel.done && !was_done) begin
                chain_dones++;
                chain_core_cycles+=dut.accel.cycles;
            end
            if (dut.cim_access && !dut.mem_write) begin
                chain_shared_reads++;
                if (dut.b_word >= 14'h1800 && dut.b_word < 14'h1800 + chain_words) begin
                    if (chain_mid_writes != chain_words) $fatal(1, "Accelerator consumed an uncommitted intermediate");
                    chain_mid_reads++;
                end
            end
            if (dut.accel.retain_write) begin
                if (chain_method < 3 || !dut.cim_access || !dut.mem_write ||
                    int'(dut.accel.retain_addr) != int'(dut.b_word)-32'h1800 ||
                    dut.accel.retain_addr >= chain_words || chain_copied[dut.accel.retain_addr])
                    $fatal(1, "Wrong retained address or duplicate SRAM commit");
                chain_copied[dut.accel.retain_addr]=1;
                chain_copies++;
            end
            if (dut.accel.spad_read && dut.accel.replay_intermediate &&
                (chain_copies != chain_words || !chain_copied[dut.accel.spad_addr] ||
                 !chain_copied[dut.accel.spad_addr+11'd1]))
                $fatal(1, "Retained replay before completing the current intermediate");
            if (dut.cpu_store || (dut.cim_access && dut.mem_write)) begin
                if (((dut.b_word >= 14'h1800 && dut.b_word < 14'h1800 + chain_words) ||
                     (dut.b_word >= 14'h2000 && dut.b_word < 14'h2000 + chain_words)) &&
                    dut.cpu_store != (chain_method == 2))
                    $fatal(1, "Result commit came from the wrong engine");
                if (dut.b_word >= 14'h1800 && dut.b_word < 14'h1800 + chain_words)
                    chain_mid_writes++;
                if (dut.b_word >= 14'h2000 && dut.b_word < 14'h2000 + chain_words) begin
                    if (chain_mid_writes != chain_words) $fatal(1, "Early layer-two write");
                    chain_final_writes++;
                end
            end
            if (!dut.cpu_wen && dut.cpu_addr == 32'h80108000 + 4*(chain_words-1) &&
                chain_final_writes == chain_words)
                chain_final_read = 1;
        end
        if (!chain_test && dut.sw_active && dut.cpu_store && dut.cpu_store_word >= 14'h2000 &&
            dut.cpu_store_word < 14'h27d0) begin
            software_output_words++;
            last_software_commit = dut.sw_cycles+1;
        end
        if (dut.run_n && dut.cpu_wen && dut.cpu_mask == 2'b10 && dut.cpu_addr == dut.SW_TIMER) begin
            if (chain_test && dut.cpu_wdata[0]) begin
                chain_starts=0; chain_dones=0; chain_core_cycles=0;
                chain_mid_writes=0; chain_final_writes=0; chain_final_read=0;
                chain_mid_reads=0; chain_shared_reads=0; chain_copies=0; chain_copied='0; chain_prefetches=0;
                chain_early_writes=0; chain_handoffs=0;
            end else if (chain_test) begin
                if (!dut.sw_active || chain_mid_writes != chain_words || chain_final_writes != chain_words ||
                    chain_starts != chain_expected_starts || chain_dones != chain_starts || !chain_final_read ||
                    chain_mid_reads != (chain_method < 2 ? chain_words : 0) ||
                    chain_copies != (chain_method >= 3 ? chain_words : 0) ||
                    ((chain_prefetches != 0) != (chain_method >= 4 && chain_words > 16)) ||
                    ((chain_early_writes != 0) != (chain_method == 5)) ||
                    ((chain_handoffs != 0) != (chain_method == 5 && chain_words > 16)) ||
                    chain_shared_reads != (chain_method == 2 ? 0 : 2432 + chain_words + chain_mid_reads))
                    $fatal(1, "Incomplete chain timer window method=%0d starts=%0d done=%0d mid=%0d final=%0d read=%0d",
                           chain_method, chain_starts, chain_dones, chain_mid_writes, chain_final_writes, chain_final_read);
                $display("CHAIN_WINDOW method=%0d starts=%0d done=%0d mid_words=%0d final_words=%0d core_cycles=%0d shared_reads=%0d mid_reads=%0d retained_words=%0d prefetches=%0d early_writes=%0d same_edge_handoffs=%0d",
                         chain_method, chain_starts, chain_dones, chain_mid_writes, chain_final_writes, chain_core_cycles,
                         chain_shared_reads, chain_mid_reads, chain_copies, chain_prefetches,
                         chain_early_writes, chain_handoffs);
                chain_windows++;
            end else if (dut.cpu_wdata[0]) begin
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
                    if (chain_test) begin
                        if (chain_windows != 2*chain_methods) $fatal(1, "Missing complete chain timer windows");
                    end else begin
                        if (reset_count != 2) $fatal(1, "Expected two warm resets");
                        if (software_runs != 2) $fatal(1, "Expected two complete software timer windows");
                    end
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
        chain_test = $test$plusargs("TEST_CHAIN");
        chain_control_test = $test$plusargs("TEST_CHAIN_CONTROL");
        retain_test = $test$plusargs("TEST_RETAIN");
        prefetch_test = $test$plusargs("TEST_PREFETCH");
        early_write_test = $test$plusargs("TEST_EARLY_WRITE");
        if (!counter_test && !chain_control_test) begin
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
        if (chain_control_test) fork
            test_chain_control();
            begin repeat (20000) @(posedge clk); $fatal(1, "Chain control test timed out"); end
        join
        repeat (chain_test ? 9000000 : 4000000) @(posedge clk);
        $fatal(1, "RV32IM firmware timed out");
    end
endmodule
