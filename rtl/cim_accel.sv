`timescale 1ns/1ps
// Original portable digital peripheral. Local reads return >=1 clock after acceptance.
module cim_accel #(
 parameter bit TURNAROUND=1,
 parameter int INPUT_CACHE=0 // 0: bypass, 1: word, 2: paired, 3: retain, 4: prefetch, 5: early writeback
) (
 input logic clk, rst_n,
 input logic cfg_valid, cfg_write,
 input logic [7:0] cfg_addr,
 input logic [31:0] cfg_wdata,
 output logic cfg_ready,
 output logic [31:0] cfg_rdata,
 output logic start_accepted,
 output logic mem_valid, mem_write,
 output logic [31:0] mem_addr, mem_wdata,
 output logic [3:0] mem_wstrb,
 input logic mem_ready, mem_rvalid,
 input logic [31:0] mem_rdata
);
 localparam IDLE=0, PARAM=1, WEIGHT=2, RUN=3;
 localparam RD_PARAM=0, RD_WEIGHT=1, RD_INPUT=2;
 localparam BANKED_REPLAY=INPUT_CACHE>=2;
 localparam INTERLAYER_CACHE=INPUT_CACHE>=3;
 localparam PREFETCH_REPLAY=INPUT_CACHE>=4;
 localparam EARLY_WRITEBACK=INPUT_CACHE==5;
 localparam [3:0] REPLAY_LAST=BANKED_REPLAY ? 4'd14 : 4'd15;
 logic [1:0] state;
 logic busy, done, error;
 logic [31:0] shadow_m, shadow_a, shadow_w, shadow_p, shadow_y, shadow_mode;
 logic [31:0] a_base,w_base,p_base,y_base;
 logic [31:0] shadow_w2,shadow_p2,shadow_y2,w2_base,p2_base,y2_base;
 logic chain_pending, retain_intermediate, prefetch_enabled;
 logic early_write_enabled;
 logic prefetch_pending, prefetch_ctx;
 logic [7:0] task_m, next_p;
 logic mode;
 logic [2:0] tile;
 logic [31:0] cycles, mem_wait, macro_cycles;
 logic [7:0] load_word;
 logic signed [31:0] bias[0:7], multiplier[0:7], shift[0:7];
 logic rd_pending;
 logic request_valid;
 logic [31:0] request_addr, rd_next_addr;
 logic [1:0] req_kind, rd_kind;
 logic req_ctx, rd_ctx;
 logic [7:0] req_index, rd_index;
 logic req_last;
 logic [31:0] weight_low;
 logic w_valid,w_ready;
 logic [5:0] w_row;
 logic [63:0] w_data;
 logic mac_start,mac_ready,mac_busy,mac_valid;
 logic [63:0] a_plane;
 logic [223:0] mac_data;
 logic [1:0] live, input_ready, issued_low, issued_high, recon_done, output_ready;
 logic [1:0] first_word_ready;
 logic [7:0] position[0:1];
 logic [4:0] fill_word[0:1];
 logic [255:0] input_low[0:1],input_high[0:1];
 logic spad_active, spad_ctx, spad_rvalid, spad_result_ctx;
 logic [3:0] spad_index, spad_result_index;
 logic [31:0] spad_rdata, spad_rdata_hi;
 logic [31:0] intermediate_low, intermediate_high;
 logic signed [31:0] partial[0:1][0:7];
 logic [63:0] output_bytes[0:1];
 logic [3:0] quant_index[0:1];
 logic [1:0] write_index;
 // Raw slots are reserved before a non-stallable macro starts.
 logic [1:0] raw_valid, raw_reserved;
 logic [223:0] raw_data[0:1];
 logic raw_ctx[0:1],raw_high[0:1];
 logic flight_slot;
 logic plane_ctx,plane_high;
 logic [1:0] plane_index;
 logic sched_valid,sched_ctx,sched_high,sched_slot;
 logic q_valid,q_ctx;
 logic q_result_valid,q_result_ctx;
 logic [2:0] q_result_channel;
 logic [7:0] q_value;
 logic signed [31:0] q_acc,q_mul,q_shift;
 integer c,j,k,s;
 logic signed [31:0] native_low,native_high,contribution;

 assign start_accepted = rst_n && cfg_valid && cfg_write && cfg_addr==8'h00 &&
                         cfg_wdata[0] && !busy && shadow_m>=1 && shadow_m<=125 &&
                         shadow_mode<=1 && ((shadow_a|shadow_w|shadow_p|shadow_y)&32'h3)==0 &&
                         (!cfg_wdata[2] || ((shadow_w2|shadow_p2|shadow_y2)&32'h3)==0) &&
                         (!cfg_wdata[3] || (INTERLAYER_CACHE && cfg_wdata[2])) &&
                         (!cfg_wdata[4] || (PREFETCH_REPLAY && cfg_wdata[3])) &&
                         (!cfg_wdata[5] || (EARLY_WRITEBACK && cfg_wdata[4] && shadow_mode==1));

 // A returning input word releases the single read credit on this edge.
 // Only offer the next word of the same context, with ready writes taking
 // precedence. If stalled, the ordinary request registers hold the offer.
 wire read_return = rd_pending && mem_rvalid;
 wire [1:0] write_ready = output_ready | (first_word_ready & ~write_index);
 wire input_follow = TURNAROUND && rst_n && !request_valid && read_return && state==RUN &&
                     rd_kind==RD_INPUT && rd_index<15 && write_ready==0;
 wire read_accept = mem_valid && mem_ready && !mem_write;
 wire external_input = read_return && rd_kind==RD_INPUT;
 wire replay_intermediate = INTERLAYER_CACHE && retain_intermediate && !chain_pending;
 wire early_writeback = EARLY_WRITEBACK && early_write_enabled && replay_intermediate;
 wire write_commit = mem_valid && mem_ready && mem_write;
 wire retain_write = INTERLAYER_CACHE && rst_n && retain_intermediate && chain_pending &&
                     mem_valid && mem_ready && mem_write;
 wire [10:0] retain_addr = {position[req_ctx][6:0], tile, req_last};
 wire spad_write = INPUT_CACHE && rst_n && external_input && tile==0;
 wire spad_read = INPUT_CACHE && rst_n && spad_active;
 // The old row still owns its output context. Its input slot becomes free
 // after the last high-slice plane, even when SRAM writeback is stalled.
 wire prefetch_slot0 = issued_high[0] && !(mac_busy && !plane_ctx);
 wire prefetch_slot1 = issued_high[1] && !(mac_busy && plane_ctx);
 wire prefetch_start = PREFETCH_REPLAY && prefetch_enabled && replay_intermediate &&
                       state==RUN && mode && live==2'b11 && input_ready==2'b11 &&
                       next_p<task_m && !prefetch_pending && !spad_active && !spad_rvalid &&
                       (prefetch_slot0 || prefetch_slot1);
 wire allocate_ctx = prefetch_pending ? prefetch_ctx : live[0];
 // The registered write owns the old tag through acceptance. Reload that
 // context on the same edge only after both the write and replay can retire.
 wire retiring_prefetch_ctx = early_writeback && write_commit && req_last && req_ctx==prefetch_ctx;
 wire allocate_row = prefetch_pending ? ((!live[prefetch_ctx] || retiring_prefetch_ctx) &&
                                        !spad_active && !spad_rvalid) :
                     (next_p<task_m && ((!mode && live==0) || (mode && live!=2'b11)));
 wire [6:0] replay_row = prefetch_pending ? next_p[6:0] : position[spad_ctx][6:0];
 wire [10:0] spad_addr = spad_write ? {position[rd_ctx][6:0], rd_index[3:0]} :
                                      {replay_row, spad_index};
 wire input_pair = BANKED_REPLAY && spad_rvalid;
 wire input_ctx = spad_rvalid ? spad_result_ctx : rd_ctx;
 wire [3:0] input_index = spad_rvalid ? spad_result_index : rd_index[3:0];
 wire [31:0] input_data = spad_rvalid ? (replay_intermediate ? intermediate_low : spad_rdata) : mem_rdata;
 wire [31:0] input_data_hi = replay_intermediate ? intermediate_high : spad_rdata_hi;
 wire [3:0] paired_index = input_index | 4'd1;
 assign mem_valid = request_valid || input_follow;
 assign mem_addr = input_follow ? rd_next_addr : request_addr;

 cim_macro macro_unit(.clk(clk),.rst_n(rst_n),.w_valid(w_valid),.w_ready(w_ready),
  .w_row(w_row),.w_data(w_data),.start(mac_start),.start_ready(mac_ready),
  .a_plane(a_plane),.busy(mac_busy),.result_valid(mac_valid),.result_data(mac_data));
 requant quant_unit(.clk(clk),.enable(q_valid),.acc(q_acc),
  .multiplier(q_mul),.shift(q_shift),.value(q_value));

 if(INTERLAYER_CACHE) begin : interlayer
  // Store only accepted SRAM writes. The accepted request owns row and word
  // through stalls. Stage two starts after the final write drains.
  for(genvar bank=0;bank<2;bank++) begin : lane
   (* ram_style = "block" *) logic [31:0] interlayer_ram[0:1023];
   logic [31:0] read_data;
   wire [9:0] address = retain_write ? retain_addr[10:1] : spad_addr[10:1];
   always_ff @(posedge clk) begin
    if(retain_write && retain_addr[0]==(bank==1)) interlayer_ram[address]<=mem_wdata;
    else if(spad_read && replay_intermediate) read_data<=interlayer_ram[address];
   end
   if(bank==0) assign intermediate_low=read_data;
   else assign intermediate_high=read_data;
  end
 end else begin : no_interlayer
  assign {intermediate_low,intermediate_high}='0;
 end

 if(INPUT_CACHE) begin : cache
  // The first tile overwrites all words used by a task before any replay.
  // The response uses the old external tag, including with read turnaround.
  if(BANKED_REPLAY) begin : paired
   for(genvar bank=0;bank<2;bank++) begin : lane
    (* ram_style = "block" *) logic [31:0] input_spad[0:1023];
    logic [31:0] read_data;
    always_ff @(posedge clk) begin
     if(spad_write && spad_addr[0]==(bank==1)) input_spad[spad_addr[10:1]]<=mem_rdata;
     else if(spad_read && !replay_intermediate) read_data<=input_spad[spad_addr[10:1]];
    end
    if(bank==0) assign spad_rdata=read_data;
    else assign spad_rdata_hi=read_data;
   end
  end else begin : single_word
   (* ram_style = "block" *) logic [31:0] input_spad[0:2047];
   always_ff @(posedge clk) begin
    if(spad_write) input_spad[spad_addr]<=mem_rdata;
    else if(spad_read) spad_rdata<=input_spad[spad_addr];
   end
   assign spad_rdata_hi='0;
  end
  always_ff @(posedge clk) begin
   if(!rst_n) begin
    spad_active<=0;spad_ctx<=0;spad_index<=0;
    spad_rvalid<=0;spad_result_ctx<=0;spad_result_index<=0;
   end else begin
    spad_rvalid<=spad_read;
    if(spad_read) begin
     spad_result_ctx<=spad_ctx;
     spad_result_index<=spad_index;
     spad_index<=spad_index+(BANKED_REPLAY ? 4'd2 : 4'd1);
     if(spad_index==REPLAY_LAST) spad_active<=0;
    end else if(prefetch_start) begin
     spad_active<=1;spad_ctx<=!prefetch_slot0;spad_index<=0;
    end else if(!prefetch_pending && state==RUN && (tile!=0 || replay_intermediate)) begin
     // Exclude the context of the last word still in the return stage.
     if(live[0] && !input_ready[0] && !(spad_rvalid && !spad_result_ctx)) begin
      spad_active<=1;spad_ctx<=0;spad_index<=0;
     end else if(live[1] && !input_ready[1] && !(spad_rvalid && spad_result_ctx)) begin
      spad_active<=1;spad_ctx<=1;spad_index<=0;
     end
    end
   end
  end
 end else begin : no_cache
  assign {spad_active,spad_ctx,spad_index,spad_rvalid,spad_result_ctx,spad_result_index,spad_rdata,spad_rdata_hi}='0;
 end

 always_comb begin
  cfg_ready=1'b1;
  cfg_rdata=0;
  case(cfg_addr)
   8'h04: cfg_rdata={29'b0,error,done,busy};
   8'h08: cfg_rdata=shadow_m;
   8'h0c: cfg_rdata=shadow_a;
   8'h10: cfg_rdata=shadow_w;
   8'h14: cfg_rdata=shadow_p;
   8'h18: cfg_rdata=shadow_y;
   8'h1c: cfg_rdata=shadow_mode;
   8'h20: cfg_rdata=cycles;
   8'h24: cfg_rdata=mem_wait;
   8'h28: cfg_rdata=macro_cycles;
   8'h2c: cfg_rdata=shadow_w2;
   8'h30: cfg_rdata=shadow_p2;
   8'h34: cfg_rdata=shadow_y2;
   default: cfg_rdata=0;
  endcase
  sched_valid=0; sched_ctx=0; sched_high=0;
  sched_slot=raw_valid[0] || raw_reserved[0];
  if(state==RUN && !( &(raw_valid | raw_reserved))) begin
   // Complete both slices of older blocks first. A block retains its input slot.
   for(integer x=1;x>=0;x=x-1)
    if(live[x] && input_ready[x] && !issued_high[x]) begin
     sched_valid=1; sched_ctx=(x==1); sched_high=issued_low[x];
    end
  end
  mac_start=sched_valid && mac_ready;
  a_plane=0;
  for(integer x=0;x<64;x=x+1)
   if(plane_high) a_plane[x]=input_high[plane_ctx][4*x+3-plane_index];
   else a_plane[x]=input_low[plane_ctx][4*x+3-plane_index];
  q_valid=0; q_ctx=0;
  for(integer x=1;x>=0;x=x-1)
   if(state==RUN && live[x] && recon_done[x] && !quant_index[x][3]) begin
    q_valid=1; q_ctx=(x==1);
   end
  q_acc=partial[q_ctx][quant_index[q_ctx][2:0]];
  q_mul=multiplier[quant_index[q_ctx][2:0]];
  q_shift=shift[quant_index[q_ctx][2:0]];
 end

 always_ff @(posedge clk) begin
  if(!rst_n) begin
   state<=IDLE; busy<=0;done<=0;error<=0;
   shadow_m<=1;shadow_a<=0;shadow_w<=0;shadow_p<=0;shadow_y<=0;shadow_mode<=0;
   shadow_w2<=0;shadow_p2<=0;shadow_y2<=0;w2_base<=0;p2_base<=0;y2_base<=0;
   chain_pending<=0;retain_intermediate<=0;
   prefetch_enabled<=0;prefetch_pending<=0;prefetch_ctx<=0;
   early_write_enabled<=0;first_word_ready<=0;
   a_base<=0;w_base<=0;p_base<=0;y_base<=0;task_m<=0;mode<=0;tile<=0;next_p<=0;
   cycles<=0;mem_wait<=0;macro_cycles<=0;
   request_valid<=0;mem_write<=0;request_addr<=0;mem_wdata<=0;mem_wstrb<=0;
   rd_pending<=0;rd_next_addr<=0;req_kind<=0;rd_kind<=0;req_ctx<=0;rd_ctx<=0;
   req_index<=0;rd_index<=0;req_last<=0;load_word<=0;weight_low<=0;
   w_valid<=0;w_row<=0;w_data<=0;
   live<=0;input_ready<=0;issued_low<=0;issued_high<=0;recon_done<=0;output_ready<=0;
   raw_valid<=0;raw_reserved<=0;flight_slot<=0;plane_ctx<=0;plane_high<=0;plane_index<=0;
   write_index<=0;
   q_result_valid<=0;q_result_ctx<=0;q_result_channel<=0;
   for(c=0;c<2;c=c+1) begin
    position[c]<=0;fill_word[c]<=0;input_low[c]<=0;input_high[c]<=0;
    output_bytes[c]<=0;quant_index[c]<=0;raw_data[c]<=0;raw_ctx[c]<=0;raw_high[c]<=0;
    for(j=0;j<8;j=j+1) partial[c][j]<=0;
   end
   for(j=0;j<8;j=j+1) begin bias[j]<=0;multiplier[j]<=0;shift[j]<=0;end
  end else begin
   q_result_valid<=q_valid;
   rd_pending<=(rd_pending && !mem_rvalid) || read_accept;
   if(busy) begin
    cycles<=cycles+1;
    if(mem_valid && !mem_ready) mem_wait<=mem_wait+1;
    if(mac_busy) macro_cycles<=macro_cycles+1;
   end
   if(cfg_valid && cfg_write) begin
    case(cfg_addr)
     8'h08: shadow_m<=cfg_wdata;
     8'h0c: shadow_a<=cfg_wdata;
     8'h10: shadow_w<=cfg_wdata;
     8'h14: shadow_p<=cfg_wdata;
     8'h18: shadow_y<=cfg_wdata;
     8'h1c: shadow_mode<=cfg_wdata;
     8'h2c: shadow_w2<=cfg_wdata;
     8'h30: shadow_p2<=cfg_wdata;
     8'h34: shadow_y2<=cfg_wdata;
     8'h00: begin
      if(cfg_wdata[1]) done<=0;
      if(cfg_wdata[0]) begin
       if(!start_accepted) error<=1;
       else begin
        busy<=1;done<=0;error<=0;state<=PARAM;
        task_m<=shadow_m[7:0];a_base<=shadow_a;w_base<=shadow_w;
        p_base<=shadow_p;y_base<=shadow_y;mode<=shadow_mode[0];
        chain_pending<=cfg_wdata[2];
        retain_intermediate<=cfg_wdata[3];
        prefetch_enabled<=cfg_wdata[4];prefetch_pending<=0;
        early_write_enabled<=EARLY_WRITEBACK && cfg_wdata[5];first_word_ready<=0;
        w2_base<=shadow_w2;p2_base<=shadow_p2;y2_base<=shadow_y2;
        tile<=0;next_p<=0;load_word<=0;cycles<=0;mem_wait<=0;macro_cycles<=0;
        live<=0;input_ready<=0;issued_low<=0;issued_high<=0;recon_done<=0;output_ready<=0;
        raw_valid<=0;raw_reserved<=0;write_index<=0;rd_pending<=0;request_valid<=0;
       end
      end
     end
     default: ;
    endcase
   end

   if(w_valid && w_ready) begin
    w_valid<=0;
    if(load_word==128) begin state<=RUN;load_word<=0;next_p<=0;end
   end

   // Request registers are never changed while valid && !ready.
   if(request_valid && mem_ready) request_valid<=0;
   if(input_follow && !mem_ready) begin
    request_valid<=1;request_addr<=rd_next_addr;
    req_kind<=RD_INPUT;req_ctx<=rd_ctx;req_index<=rd_index+1'b1;
   end
   if(read_accept) begin
    rd_kind<=input_follow ? RD_INPUT : req_kind;
    rd_ctx<=input_follow ? rd_ctx : req_ctx;
    rd_index<=input_follow ? rd_index+1'b1 : req_index;
    if(TURNAROUND && (input_follow || req_kind==RD_INPUT)) rd_next_addr<=mem_addr+32'd4;
   end
   if(write_commit) begin
     if(req_last) begin
      live[req_ctx]<=0;output_ready[req_ctx]<=0;write_index[req_ctx]<=0;
      first_word_ready[req_ctx]<=0;
     end else write_index[req_ctx]<=1;
   end
   if(read_return) begin
    // Nonblocking updates above preserve the old tag for this response,
    // including when the same edge accepts its successor.
    case(rd_kind)
     RD_PARAM: begin
      case(rd_index%3)
       0: bias[rd_index/3]<= $signed(mem_rdata);
       1: begin
        multiplier[rd_index/3]<=$signed(mem_rdata);
        if(mem_rdata[31]) begin state<=IDLE;busy<=0;error<=1;end
       end
       2: begin
        shift[rd_index/3]<=$signed(mem_rdata);
        if($signed(mem_rdata)>0 || $signed(mem_rdata)<-31) begin state<=IDLE;busy<=0;error<=1;end
       end
      endcase
      load_word<=load_word+1;
      if(rd_index==23 && $signed(mem_rdata)<=0 && $signed(mem_rdata)>=-31) begin
       state<=WEIGHT;load_word<=0;
      end
     end
     RD_WEIGHT: begin
      load_word<=load_word+1;
      if(!rd_index[0]) weight_low<=mem_rdata;
      else begin w_valid<=1;w_row<=rd_index[6:1];w_data<={mem_rdata,weight_low};end
     end
     default: ;
    endcase
   end
   if(external_input || spad_rvalid) begin
    for(k=0;k<4;k=k+1) begin
     input_low[input_ctx][(input_index*4+k)*4 +:4]<=input_data[k*8 +:4];
     input_high[input_ctx][(input_index*4+k)*4 +:4]<={~input_data[k*8+7],input_data[k*8+4 +:3]};
    end
    if(input_pair) for(k=0;k<4;k=k+1) begin
     input_low[input_ctx][(paired_index*4+k)*4 +:4]<=input_data_hi[k*8 +:4];
     input_high[input_ctx][(paired_index*4+k)*4 +:4]<={~input_data_hi[7+k*8],input_data_hi[4+k*8 +:3]};
    end
    if(!prefetch_pending) begin
     fill_word[input_ctx]<=fill_word[input_ctx]+(input_pair ? 5'd2 : 5'd1);
     if(input_index==(input_pair ? 4'd14 : 4'd15)) input_ready[input_ctx]<=1;
    end
   end

   // One shared 32-bit port; at most one outstanding read and a reserved destination.
   if(busy && !mem_valid && !rd_pending && !w_valid) begin
    if(state==PARAM) begin
     request_valid<=1;mem_write<=0;mem_wstrb<=0;
     request_addr<=p_base+tile*96+load_word*4;req_kind<=RD_PARAM;req_index<=load_word;
    end else if(state==WEIGHT) begin
     request_valid<=1;mem_write<=0;mem_wstrb<=0;
     request_addr<=w_base+tile*512+load_word*4;req_kind<=RD_WEIGHT;req_index<=load_word;
    end else if(state==RUN) begin
     if(write_ready[0] || write_ready[1]) begin
      // Priority can only change between accepted requests, never under backpressure.
      if(write_ready[0]) begin
       req_ctx<=0;req_last<=write_index[0];
       request_addr<=y_base+position[0]*64+tile*8+write_index[0]*4;
       mem_wdata<=output_bytes[0][write_index[0]*32 +:32];
      end else begin
       req_ctx<=1;req_last<=write_index[1];
       request_addr<=y_base+position[1]*64+tile*8+write_index[1]*4;
       mem_wdata<=output_bytes[1][write_index[1]*32 +:32];
      end
      request_valid<=1;mem_write<=1;mem_wstrb<=4'hf;
     end else if((!INPUT_CACHE || (tile==0 && !replay_intermediate)) &&
                 ((live[0] && !input_ready[0]) || (live[1] && !input_ready[1]))) begin
      request_valid<=1;mem_write<=0;mem_wstrb<=0;req_kind<=RD_INPUT;
      if(live[0] && !input_ready[0]) begin
       req_ctx<=0;req_index<={3'b0,fill_word[0]};
       request_addr<=a_base+position[0]*64+fill_word[0]*4;
      end else begin
       req_ctx<=1;req_index<={3'b0,fill_word[1]};
       request_addr<=a_base+position[1]*64+fill_word[1]*4;
      end
     end
    end
   end

   if(state==RUN) begin
    // MODE=0 admits only one context. MODE=1 uses exactly the same arithmetic.
    if(prefetch_start) begin
     prefetch_pending<=1;prefetch_ctx<=!prefetch_slot0;
    end
    if(allocate_row) begin
     live[allocate_ctx]<=1;position[allocate_ctx]<=next_p;
     fill_word[allocate_ctx]<=prefetch_pending ? 5'd16 : 5'd0;
     input_ready[allocate_ctx]<=prefetch_pending;
     issued_low[allocate_ctx]<=0;issued_high[allocate_ctx]<=0;
     recon_done[allocate_ctx]<=0;output_ready[allocate_ctx]<=0;
     first_word_ready[allocate_ctx]<=0;
     quant_index[allocate_ctx]<=0;write_index[allocate_ctx]<=0;
     prefetch_pending<=0;
     next_p<=next_p+1;
    end
    if(mac_start) begin
     raw_reserved[sched_slot]<=1;raw_ctx[sched_slot]<=sched_ctx;raw_high[sched_slot]<=sched_high;
     flight_slot<=sched_slot;plane_ctx<=sched_ctx;plane_high<=sched_high;plane_index<=0;
     if(sched_high) issued_high[sched_ctx]<=1;else issued_low[sched_ctx]<=1;
    end else if(mac_busy) plane_index<=plane_index+1;
    if(mac_valid) begin
     raw_data[flight_slot]<=mac_data;raw_valid[flight_slot]<=1;raw_reserved[flight_slot]<=0;
    end
    // A popped low-slice packet lives in the block partial sum until the high slice arrives.
    for(s=0;s<2;s=s+1) if(raw_valid[s]) begin
     for(j=0;j<8;j=j+1) begin
      native_low=$signed({18'b0,raw_data[s][j*28 +:14]});
      native_high=$signed({{18{raw_data[s][j*28+27]}},raw_data[s][j*28+14 +:14]});
      contribution=native_low+(native_high<<<4);
      if(raw_high[s]) partial[raw_ctx[s]][j]<=partial[raw_ctx[s]][j]+(contribution<<<4)+bias[j];
      else partial[raw_ctx[s]][j]<=contribution;
     end
     if(raw_high[s]) recon_done[raw_ctx[s]]<=1;
     raw_valid[s]<=0;
    end
    if(q_valid) begin
     q_result_ctx<=q_ctx;
     q_result_channel<=quant_index[q_ctx][2:0];
     quant_index[q_ctx]<=quant_index[q_ctx]+1;
    end
    if(q_result_valid) begin
     output_bytes[q_result_ctx][q_result_channel*8 +:8]<=q_value;
     if(early_writeback && q_result_channel==3) first_word_ready[q_result_ctx]<=1;
     if(q_result_channel==7) output_ready[q_result_ctx]<=1;
    end
    if(next_p==task_m && live==0 && raw_valid==0 && raw_reserved==0 &&
       !mac_busy && !mac_valid && !mem_valid && !rd_pending && !q_result_valid &&
       !spad_active && !spad_rvalid && !prefetch_pending) begin
     if(tile!=7) begin tile<=tile+1;load_word<=0;state<=PARAM;next_p<=0;end
     else if(chain_pending) begin
      // Every intermediate write has committed. Tile zero either reads
      // the retained words or fills the input cache from shared SRAM.
      chain_pending<=0;
      a_base<=y_base;w_base<=w2_base;p_base<=p2_base;y_base<=y2_base;
      tile<=0;load_word<=0;state<=PARAM;next_p<=0;
     end else begin busy<=0;done<=1;state<=IDLE;retain_intermediate<=0;end
    end
   end
  end
 end
endmodule
