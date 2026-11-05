`timescale 1ns/1ps
module tb_accel;
 reg clk=0; always #5 clk=~clk;
 reg rst_n=0,cfg_valid=0,cfg_write=0;
 reg [7:0] cfg_addr=0;
 reg [31:0] cfg_wdata=0;
 wire cfg_ready,start_accepted; wire [31:0] cfg_rdata;
 wire mem_valid,mem_write; wire [31:0] mem_addr,mem_wdata;
 wire [3:0] mem_wstrb;
 reg mem_ready=0,mem_rvalid=0; reg [31:0] mem_rdata=0;
 reg [7:0] memory[0:65535],golden[0:7999];
 reg [7:0] case_m[0:15];
 reg written[0:7999];
 cim_accel dut(.*);
 integer clock_count=0,read_count=0,write_count=0,response_count=0,macro_count=0;
 integer first_block[0:7],last_block[0:7],service_count=0;
 integer pending_delay=0,final_hold=0,early_hold=0,task_m=1;
 reg read_pending=0,active=0,hold_seen=0;
 reg observed_outstanding=0,fixed_memory=0,vcd_trace=0;
 reg check_rollover=0,expected_ctx;
 reg [7:0] expected_index;
 reg [1:0] previous_live, committed_release;
 reg [31:0] pending_addr=0;
 reg held=0; reg [68:0] held_request;
 integer i,j,case_id,mode_id,ncases=4,timeout_cycles;
 integer cycles_result,reads_result,writes_result;
 reg [31:0] status;
 string vector_file;
 integer summary,steady_summary,trace,profile;
 integer port_stall, response_wait, idle_other;
 integer follow_accepts, follow_stalls, weight_commits;
 reg p1_only=0,expected_busy_error=0,two_live_seen=0;

 // Requests may wait. A read response cannot be paused and returns once.
 // Pattern is deterministic, with 1..4 cycles of memory service delay.
 always @(negedge clk) begin
  mem_ready = rst_n && (fixed_memory || (((service_count%7)!=2) && ((service_count%11)!=5)));
  if(!fixed_memory && read_pending) mem_ready=0;
  if(!fixed_memory && active && task_m>1 && mem_valid && mem_write && mem_addr==32'h8000 && early_hold<96) begin
   mem_ready=0;early_hold=early_hold+1;
  end
  if(!fixed_memory && active && mem_valid && mem_write && mem_addr==32'h8000+64*task_m-4 && !hold_seen) begin
   mem_ready=0;
   final_hold=final_hold+1;
   if(final_hold==24) begin hold_seen=1; end
  end
 end

 always @(posedge clk) begin
  clock_count=clock_count+1;
  service_count=service_count+1;
  mem_rvalid<=0;
  if(!rst_n) begin
   read_pending=0;observed_outstanding=0;held=0;check_rollover=0;mem_rvalid<=0;
  end else begin
   if(check_rollover && (!dut.rd_pending || dut.rd_ctx!==expected_ctx || dut.rd_index!==expected_index))
    $fatal(1,"read credit or tag lost on simultaneous response/request");
   check_rollover=dut.input_follow && mem_ready;
   if(dut.input_follow) begin
    if(!mem_rvalid || !dut.rd_pending || dut.rd_index>=15 || mem_write ||
       mem_addr!==dut.a_base + 64*dut.position[dut.rd_ctx] + 4*(dut.rd_index+1))
     $fatal(1,"continuation did not name the next word of the old context");
    expected_ctx=dut.rd_ctx;
    expected_index=dut.rd_index+1;
   end
   if(mem_rvalid && !observed_outstanding) $fatal(1,"unsolicited read response");
   if(mem_valid && mem_ready && !mem_write && observed_outstanding && !mem_rvalid)
    $fatal(1,"more than one outstanding read");
   observed_outstanding=(observed_outstanding && !mem_rvalid) || (mem_valid && mem_ready && !mem_write);
   if(mem_rvalid) response_count++;
   if(active && dut.busy) begin
    if(mem_valid && !mem_ready) port_stall++;
    else if(dut.rd_pending && !mem_rvalid) response_wait++;
    else if(!mem_valid) idle_other++;
    if(trace && case_id==0 && mode_id==0)
     $fwrite(trace,"%0d,%0d,%0d,%08h,%b,%b,%b,%b,%b\n",dut.cycles+1,dut.state,dut.req_kind,
             mem_addr,mem_valid,mem_ready,mem_write,mem_rvalid,dut.rd_pending);
   end
   if(active) begin
    if((previous_live & ~dut.live) != committed_release)
     $fatal(1,"context release differed from final word commit");
    previous_live=dut.live;
    committed_release=0;
    if(mem_valid && mem_ready && mem_write && dut.req_last)
     committed_release[dut.req_ctx]=1;
    if(dut.w_valid && dut.w_ready) weight_commits++;
    if(dut.input_follow && mem_ready) follow_accepts++;
    if(dut.input_follow && !mem_ready) follow_stalls++;
   end
   if(held && (!mem_valid || {mem_write,mem_addr,mem_wdata,mem_wstrb}!==held_request))
    $fatal(1,"unstable stalled memory request cycle=%0d",clock_count);
   held=mem_valid && !mem_ready;
   held_request={mem_write,mem_addr,mem_wdata,mem_wstrb};
   if(read_pending) begin
    if(pending_delay==0) begin
     mem_rvalid<=1;
     mem_rdata<={memory[pending_addr+3],memory[pending_addr+2],memory[pending_addr+1],memory[pending_addr]};
     read_pending=0;
    end else pending_delay=pending_delay-1;
   end
   if(mem_valid && mem_ready) begin
    if(mem_addr>65532 || mem_addr[1:0]!=0) $fatal(1,"invalid memory address %h",mem_addr);
    if(mem_write) begin
     if(!active) $fatal(1,"write outside task");
     if(mem_wstrb!=4'hf) $fatal(1,"unexpected partial output");
     if(mem_addr<32'h8000 || mem_addr+4>32'h8000+64*task_m) $fatal(1,"write outside output");
     for(integer b=0;b<4;b=b+1) begin
      if(written[mem_addr-32'h8000+b]) $fatal(1,"duplicate output address %h",mem_addr+b);
      written[mem_addr-32'h8000+b]=1;
      memory[mem_addr+b]=mem_wdata[8*b+:8];
     end
     write_count=write_count+1;
     if(mem_addr[2:0]==4) begin
      if(first_block[(mem_addr-'h8000)%64/8]==0) first_block[(mem_addr-'h8000)%64/8]=clock_count;
      last_block[(mem_addr-'h8000)%64/8]=clock_count;
     end
    end else begin
     if(read_pending) $fatal(1,"multiple outstanding reads");
     if(fixed_memory) begin
      mem_rvalid<=1;
      mem_rdata<={memory[mem_addr+3],memory[mem_addr+2],memory[mem_addr+1],memory[mem_addr]};
     end else begin
      read_pending=1;pending_addr=mem_addr;pending_delay=service_count%4;
     end
     read_count=read_count+1;
    end
   end
   if(active && dut.done && (write_count!=16*task_m || mem_valid || dut.rd_pending ||
      dut.live!=0 || dut.raw_valid!=0 || dut.raw_reserved!=0 || dut.q_result_valid ||
      dut.mac_busy || dut.mac_valid))
    $fatal(1,"early DONE before pipeline drain and final write commit");
   if(active && dut.live==2'b11) two_live_seen=1;
   if((dut.raw_valid[0]+dut.raw_valid[1]+dut.raw_reserved[0]+dut.raw_reserved[1])>2)
    $fatal(1,"raw capacity exceeded");
   if((dut.raw_valid & dut.raw_reserved)!=0) $fatal(1,"raw slot both occupied and reserved");
   if(dut.mac_start && dut.mac_ready) begin
    if(dut.raw_valid[dut.sched_slot] || dut.raw_reserved[dut.sched_slot]) $fatal(1,"macro issued without free reservation slot");
    macro_count=macro_count+1;
    if(active && weight_commits!=64*(dut.tile+1))
     $fatal(1,"macro launched before its tile's last weight commit");
   end
  end
 end

 task automatic wr(input [7:0] addr,input [31:0] data);
  @(negedge clk);cfg_valid=1;cfg_write=1;cfg_addr=addr;cfg_wdata=data;
  @(negedge clk);cfg_valid=0;cfg_write=0;
 endtask
 task automatic rd(input [7:0] addr,output [31:0] data);
  @(negedge clk);cfg_addr=addr;cfg_valid=1;cfg_write=0;
  #1;data=cfg_rdata;
  @(negedge clk);cfg_valid=0;
 endtask
 task automatic configure(input integer m,input integer mode);
  wr('h08,m);wr('h0c,'h1000);wr('h10,'h4000);wr('h14,'h6000);wr('h18,'h8000);wr('h1c,mode);
 endtask
 task automatic check_rejected;
  wr('h00,1);repeat(8) @(negedge clk);rd('h04,status);
  if(status[0] || !status[2]) $fatal(1,"illegal task not rejected status=%h",status);
 endtask

 initial begin
  if($value$plusargs("NCASES=%d",ncases)) begin end
  if(ncases<1 || ncases>16) $fatal(1,"case manifest capacity exceeded");
  $readmemh("build/vectors/m_values.hex",case_m,0,ncases-1);
  if($test$plusargs("P1_ONLY")) begin p1_only=1;ncases=2;end
  fixed_memory=$test$plusargs("FIXED_MEMORY");
  vcd_trace=$test$plusargs("VCD_TRACE");
  summary=$fopen(fixed_memory ? "build/fixed_results.csv" : "build/results.csv","w");
  steady_summary=$fopen(fixed_memory ? "build/fixed_steady.csv" : "build/steady.csv","w");
  profile=$fopen(fixed_memory ? "build/fixed_profile.csv" : "build/variable_profile.csv","w");
  $fwrite(profile,"case,M,mode,port_stall,response_wait,idle_other\n");
  if($test$plusargs("TRACE_MEMORY")) begin
   trace=$fopen(fixed_memory ? "build/fixed_trace.csv" : "build/variable_trace.csv","w");
   $fwrite(trace,"cycle,state,kind,addr,valid,ready,write,response,pending\n");
  end
  $fwrite(summary,"case,M,mode,cycles,read_requests,write_requests,clock_edges\n");
  $fwrite(steady_summary,"case,M,mode,tile,first_block_commit,last_block_commit,interval_sum,interval_count\n");
  repeat(5) @(negedge clk);rst_n=1;
  rd('h04,status);if(status!==0) $fatal(1,"reset status=%h",status);
  configure(0,0);check_rejected();
  configure(126,0);check_rejected();
  configure(1,0);wr('h0c,'h1001);check_rejected();
  // Abort while a read is pending; both sides discard old transactions on reset.
  $readmemh("build/vectors/mem0.hex",memory);configure(1,1);wr('h00,1);
  repeat(20) @(negedge clk);rst_n=0;repeat(3) @(negedge clk);rst_n=1;
  rd('h04,status);if(status!==0 || mem_valid) $fatal(1,"reset abort did not clear state");

  // Abort with an accepted quantization result waiting to be written.
  configure(1,0);wr('h00,1);
  for(int elapsed=0; elapsed<20000 && !dut.q_result_valid; elapsed++)
   @(negedge clk);
  if(!dut.q_result_valid) $fatal(1,"quantization reset point not reached");
  rst_n=0;
  repeat(3) @(negedge clk);rst_n=1;
  rd('h04,status);
  if(status!==0 || mem_valid || dut.q_result_valid)
   $fatal(1,"quantization result survived reset");

  // Reset at a continuation offer for word 15, while word 14 returns.
  configure(1,1);wr('h00,1);
  for(int elapsed=0; elapsed<20000 && !(dut.input_follow && dut.rd_index==14); elapsed++)
   @(negedge clk);
  if(!dut.input_follow || dut.rd_index!=14) $fatal(1,"word-15 reset point not reached");
  rst_n=0;repeat(3) @(negedge clk);rst_n=1;
  rd('h04,status);
  if(status!==0 || mem_valid || dut.rd_pending) $fatal(1,"continuation survived reset");
  for(case_id=0;case_id<ncases;case_id=case_id+1) begin
   for(mode_id=0;mode_id<(p1_only?1:2);mode_id=mode_id+1) begin
    task_m=case_m[case_id];
    vector_file=$sformatf("build/vectors/mem%0d.hex",case_id);
    $readmemh(vector_file,memory);
    vector_file=$sformatf("build/vectors/gold%0d.hex",case_id);
    $readmemh(vector_file,golden,0,64*task_m-1);
    for(i=0;i<8000;i=i+1) written[i]=0;
    read_count=0;write_count=0;response_count=0;macro_count=0;final_hold=0;early_hold=0;hold_seen=0;two_live_seen=0;
    port_stall=0;response_wait=0;idle_other=0;
    previous_live=0;committed_release=0;
    follow_accepts=0;follow_stalls=0;weight_commits=0;
    for(i=0;i<8;i=i+1) begin first_block[i]=0;last_block[i]=0;end
    configure(task_m,mode_id);
    service_count=0;
    wr('h00,1);
    active=1;
    if(vcd_trace && case_id==0 && mode_id==0) begin
     $dumpfile(fixed_memory ? "build/fixed_memory.vcd" : "build/variable_memory.vcd");
     $dumpvars(0,clk,mem_valid,mem_ready,mem_write,mem_addr,mem_rvalid,dut.rd_pending,dut.req_kind);
    end
    expected_busy_error=(case_id==0 && mode_id==0);
    if(expected_busy_error) begin
     wr('h00,1);rd('h04,status);
     if(!status[0] || !status[2]) $fatal(1,"busy START did not reject while preserving task");
    end
    // Active task configuration is latched; shadow writes cannot redirect it.
    wr('h08,7);wr('h0c,'h2000);wr('h18,'ha000);
    timeout_cycles=0;status=0;
    while(!status[1]) begin
     rd('h04,status);timeout_cycles=timeout_cycles+2;
     if(status[2] && !expected_busy_error) $fatal(1,"task error case=%0d mode=%0d status=%h state=%0d",case_id,mode_id,status,dut.state);
     if(timeout_cycles>1000000) $fatal(1,"task timeout case=%0d mode=%0d state=%0d",case_id,mode_id,dut.state);
    end
    if(status[0] || write_count!=16*task_m || read_count!=response_count || observed_outstanding)
     $fatal(1,"non-drained DONE status=%h reads=%0d responses=%0d writes=%0d",status,read_count,response_count,write_count);
    if(!fixed_memory && !hold_seen) $fatal(1,"final-write backpressure not reached");
    if(!fixed_memory && task_m>1 && early_hold!=96) $fatal(1,"early finite write stall not reached");
    if(task_m>1 && mode_id==1 && !two_live_seen) $fatal(1,"two live contexts were never exercised");
    if(read_count!=8*(152+16*task_m) || macro_count!=16*task_m)
     $fatal(1,"service count mismatch reads=%0d macros=%0d",read_count,macro_count);
    if(weight_commits!=8*64 || follow_accepts==0 || (!fixed_memory && follow_stalls==0))
     $fatal(1,"missing weight/continuation coverage weights=%0d follow=%0d stalls=%0d",
            weight_commits,follow_accepts,follow_stalls);
    for(i=0;i<64*task_m;i=i+1) begin
     if(!written[i] || memory['h8000+i]!==golden[i])
      $fatal(1,"INT8 mismatch case=%0d mode=%0d p=%0d o=%0d expected=%h actual=%h written=%b",case_id,mode_id,i/64,i%64,golden[i],memory['h8000+i],written[i]);
    end
    rd('h20,status);cycles_result=status;
    $display("PASS RTL case=%0d M=%0d mode=%0d outputs=%0d cycles=%0d reads=%0d writes=%0d",case_id,task_m,mode_id,64*task_m,cycles_result,read_count,write_count);
    $fwrite(summary,"%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",case_id,task_m,mode_id,cycles_result,read_count,write_count,clock_count);
    $fwrite(profile,"%0d,%0d,%0d,%0d,%0d,%0d\n",case_id,task_m,mode_id,port_stall,response_wait,idle_other);
    if(vcd_trace && case_id==0 && mode_id==0) $dumpoff;
    if(task_m>1) for(i=0;i<8;i=i+1)
     $fwrite(steady_summary,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",case_id,task_m,mode_id,i,first_block[i],last_block[i],last_block[i]-first_block[i],task_m-1);
    repeat(10) @(negedge clk);rd('h04,status);
    if(!status[1]) $fatal(1,"DONE not sticky");
    // First completion is cleared by next legal START, others exercise ACK.
    if(!(case_id==0 && mode_id==0)) begin
     wr('h00,2);rd('h04,status);if(status[1]) $fatal(1,"ACK did not clear DONE");
    end
    active=0;
   end
  end
  for(int bad=0; bad<2; bad++) begin
   $readmemh("build/vectors/mem0.hex",memory);
   if(bad==0) memory['h6007]=8'hff; // negative multiplier
   else begin
    memory['h6008]=1;memory['h6009]=0;memory['h600a]=0;memory['h600b]=0;
   end
   configure(1,0);wr('h00,1);status=1;timeout_cycles=0;
   while(status[0]) begin rd('h04,status);timeout_cycles=timeout_cycles+2;if(timeout_cycles>1000)$fatal(1,"parameter reject timeout");end
   if(!status[2] || status[1] || mem_valid || observed_outstanding)
    $fatal(1,"parameter error failed to drain");
  end
  $display("PASS RTL protocol: stable waits, one read credit, final commits, parameter errors, and reset aborts");
  $display("PASS ALL RTL");$fclose(summary);$fclose(steady_summary);$fclose(profile);
  if(trace) $fclose(trace);
  $finish;
 end
endmodule
