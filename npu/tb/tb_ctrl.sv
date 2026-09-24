// =====================================================================
// tb_ctrl.sv -- control plane integration: ECC inject and reporting,
// hardware semaphores, queue priority, error classes, Q-Channel.
// Drives the real npu_top, not a model of it.
// =====================================================================
module tb_ctrl;
  import npu_pkg::*;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;

  logic [NMCU-1:0]             push_valid;
  logic [NMCU-1:0][QIDW-1:0]   push_qid;
  logic [NMCU-1:0][DESC_W-1:0] push_desc;
  logic [NMCU-1:0]             push_ready;

  logic m_arvalid, m_arready, m_rvalid, m_rready, m_rlast;
  logic [AXI_AW-1:0] m_araddr; logic [7:0] m_arlen;
  logic [2:0] m_arsize; logic [1:0] m_arburst;
  logic [AXI_IDW-1:0] m_arid, m_rid; logic [AXI_DW-1:0] m_rdata;
  logic m_awvalid, m_awready, m_wvalid, m_wready, m_wlast, m_bvalid, m_bready;
  logic [AXI_AW-1:0] m_awaddr; logic [7:0] m_awlen;
  logic [2:0] m_awsize; logic [1:0] m_awburst;
  logic [AXI_IDW-1:0] m_awid; logic [AXI_DW-1:0] m_wdata;
  logic [AXI_DW/8-1:0] m_wstrb;

  logic s_awvalid, s_awready, s_wvalid, s_wready, s_bvalid, s_bready;
  logic s_arvalid, s_arready, s_rvalid, s_rready;
  logic [LT_AW-1:0] s_awaddr, s_araddr;
  logic [MCUW-1:0]  s_awid, s_arid;
  logic [LT_DW-1:0] s_wdata, s_rdata;
  logic [LT_DW/8-1:0] s_wstrb;
  logic [1:0] s_bresp, s_rresp;
  logic qreqn = 1, qacceptn, qdeny, qactive;
  logic irq;

  npu_top u_dut (.*);
  logic mem_stall = 1'b0;
  axi_mem #(.LAT(4), .OOO(1)) u_mem (
    .clk(clk), .rst_n(rst_n), .stall_r(mem_stall),
    .arvalid(m_arvalid), .arready(m_arready), .araddr(m_araddr),
    .arlen(m_arlen), .arsize(m_arsize), .arburst(m_arburst), .arid(m_arid),
    .rvalid(m_rvalid), .rready(m_rready), .rdata(m_rdata),
    .rid(m_rid), .rlast(m_rlast),
    .awvalid(m_awvalid), .awready(m_awready), .awaddr(m_awaddr),
    .awlen(m_awlen), .awsize(m_awsize), .awburst(m_awburst), .awid(m_awid),
    .wvalid(m_wvalid), .wready(m_wready), .wdata(m_wdata),
    .wstrb(m_wstrb), .wlast(m_wlast),
    .bvalid(m_bvalid), .bready(m_bready));

  int errors = 0;
  task automatic chk(input string what, input logic ok);
    if (!ok) begin errors++; $display("FAIL: %s", what); end
  endtask

  // ---------------- AXI4-Lite ----------------
  task automatic csr_rd(input logic [LT_AW-1:0] a, input logic [MCUW-1:0] who,
                        output logic [31:0] d);
    @(negedge clk); s_arvalid = 1'b1; s_araddr = a; s_arid = who;
    @(posedge clk); while (!s_arready) @(posedge clk);
    @(negedge clk); s_arvalid = 1'b0; s_rready = 1'b1;
    @(posedge clk); while (!s_rvalid) @(posedge clk);
    d = s_rdata;
    @(negedge clk); s_rready = 1'b0;
  endtask

  task automatic csr_wr(input logic [LT_AW-1:0] a, input logic [MCUW-1:0] who,
                        input logic [31:0] d);
    @(negedge clk); s_awvalid = 1'b1; s_awaddr = a; s_awid = who;
    @(posedge clk); while (!s_awready) @(posedge clk);
    @(negedge clk); s_awvalid = 1'b0; s_wvalid = 1'b1; s_wdata = d; s_wstrb = '1;
    @(posedge clk); while (!s_wready) @(posedge clk);
    @(negedge clk); s_wvalid = 1'b0; s_bready = 1'b1;
    @(posedge clk); while (!s_bvalid) @(posedge clk);
    @(negedge clk); s_bready = 1'b0;
  endtask

  task automatic wait_idle();
    logic [31:0] st;
    int guard = 0;
    forever begin
      csr_rd(12'h004, 2'd0, st);
      if (st[4]) break;
      guard++;
      if (guard > 20000) begin
        chk("wait_idle timed out", 1'b0);
        break;
      end
    end
  endtask

  // ---------------- descriptor helpers ----------------
  function automatic logic [DESC_W-1:0] mk(input logic [2:0] pipe,
                                           input logic [5:0] opc,
                                           input logic [7:0] tag,
                                           input logic [191:0] pl,
                                           input logic [NEVT-1:0] wm = '0,
                                           input logic set_en = 1'b0,
                                           input logic [3:0] set_evt = '0,
                                           input logic bar_q = 1'b0,
                                           input logic vld = 1'b1);
    hdr_t h;
    h = '{rsvd: 6'd0, fp: 1'b0, bar_g: 1'b0, bar_q: bar_q, set_evt: set_evt,
          set_en: set_en, tag: tag, opc: opc, pipe: pipe, vld: vld};
    return {pl, 16'd0, wm, h};
  endfunction

  function automatic logic [191:0] dma_pl(input logic [47:0] ext,
                                          input logic [15:0] buf_a,
                                          input logic [15:0] rows,
                                          input logic [15:0] cols);
    mte_t m;
    m = '0;
    m.ext_addr    = ext;
    m.buf_addr    = buf_a;
    m.rows        = rows;
    m.cols        = cols;
    m.buf_rstride = cols;
    m.ext_rstride = 32'(cols);
    return m;
  endfunction

  task automatic push(input int port, input logic [QIDW-1:0] q,
                      input logic [DESC_W-1:0] d);
    @(negedge clk);
    push_valid       = '0;
    push_valid[port] = 1'b1;
    push_qid[port]   = q;
    push_desc[port]  = d;
    @(posedge clk);
    while (!push_ready[port]) @(posedge clk);
    @(negedge clk);
    push_valid = '0;
  endtask

  // ---------------- queue pop order observer ----------------
  logic [QIDW-1:0] pop_log [$];
  always @(posedge clk)
    if (rst_n && u_dut.u_msgq.pop_valid && u_dut.u_msgq.pop_ready)
      pop_log.push_back(u_dut.u_msgq.pop_qid);

  logic [31:0] v, v2;

  initial begin
    push_valid = '0; push_qid = '0; push_desc = '0;
    s_awvalid = 0; s_wvalid = 0; s_bready = 0;
    s_arvalid = 0; s_rready = 0; s_wstrb = '1;
    s_awaddr = 0; s_araddr = 0; s_wdata = 0; s_awid = 0; s_arid = 0;
    for (int i = 0; i < 64; i++) u_mem.mem[i] = {8{32'h1234_0000}} + i;

    repeat (4) @(posedge clk);
    rst_n = 1;
    repeat (2) @(posedge clk);

    // ================= MAGIC =================
    csr_rd(12'h000, 2'd0, v);
    chk("MAGIC", v === 32'h4E50_5502);

    // ================= hardware semaphores =================
    // read-to-acquire: the grant is decided in the transaction that
    // reported the lock free, so two readers cannot both see it free
    csr_rd(12'h100, 2'd1, v);
    chk("lock free on first read", v[0] === 1'b1);
    csr_rd(12'h100, 2'd2, v);
    chk("lock held on second read", v[0] === 1'b0 && v[16] === 1'b1);
    chk("lock owner is the first reader", v[9:8] === 2'd1);
    csr_wr(12'h100, 2'd2, 32'd0);            // non-owner release: ignored
    csr_rd(12'h100, 2'd3, v);
    chk("non-owner cannot release", v[0] === 1'b0 && v[9:8] === 2'd1);
    csr_wr(12'h100, 2'd1, 32'd0);            // owner releases
    csr_rd(12'h100, 2'd3, v);
    chk("owner release works", v[0] === 1'b1);
    csr_rd(12'h104, 2'd0, v);
    chk("locks are independent", v[0] === 1'b1);

    // ================= ECC: single-bit inject is corrected =================
    csr_wr(12'h080, 2'd0, 32'h1);            // clear counters
    csr_wr(12'h088, 2'd0, 32'h0000_0001);    // 1-bit inject, bank 0
    push(0, 3'd0, mk(3'(P_MTE_IN),  6'd0, 8'h10, dma_pl(48'h0, 16'h0000, 1, 4),
                     '0, 1'b1, 4'd0));
    push(0, 3'd0, mk(3'(P_MTE_OUT), 6'd0, 8'h11,
                     dma_pl(48'h4000, 16'h0000, 1, 4), 16'h0001));
    wait_idle();
    csr_wr(12'h088, 2'd0, 32'h0);
    csr_rd(12'h08C, 2'd0, v);
    chk("single-bit errors were corrected and counted", v != 32'd0);
    csr_rd(12'h090, 2'd0, v2);
    chk("no uncorrectable errors yet", v2 === 32'd0);
    csr_rd(12'h004, 2'd0, v);
    chk("no error flags after a corrected error", v[3:0] === 4'd0);
    for (int i = 0; i < 4; i++)
      chk($sformatf("beat %0d survived single-bit corruption", i),
          u_mem.mem[32'h200 + i] === u_mem.mem[i]);

    // ================= ECC: double-bit inject is flagged =================
    csr_wr(12'h088, 2'd0, 32'h0000_0002);    // 2-bit inject, bank 0
    push(0, 3'd0, mk(3'(P_MTE_IN),  6'd0, 8'h12, dma_pl(48'h0, 16'h0010, 1, 4),
                     '0, 1'b1, 4'd1));
    push(0, 3'd0, mk(3'(P_MTE_OUT), 6'd0, 8'h13,
                     dma_pl(48'h8000, 16'h0010, 1, 4), 16'h0002));
    wait_idle();
    csr_wr(12'h088, 2'd0, 32'h0);
    csr_rd(12'h090, 2'd0, v);
    chk("double-bit errors were flagged", v != 32'd0);
    csr_rd(12'h094, 2'd0, v);
    chk("first error location was latched", v[9:8] === 2'd0);

    // ================= illegal descriptor is discarded =================
    csr_wr(12'h080, 2'd0, 32'h1);
    push(0, 3'd0, mk(3'd7, 6'd0, 8'h20, '0));          // undefined pipe
    push(0, 3'd0, mk(3'(P_MTE_IN), 6'd0, 8'h21,
                     dma_pl(48'h0, 16'h0020, 1, 2)));  // must still run
    wait_idle();
    csr_rd(12'h004, 2'd0, v);
    chk("err_illegal raised", v[0] === 1'b1);
    chk("err_task not raised by an illegal encoding", v[2] === 1'b0);
    csr_rd(12'h008, 2'd0, v);
    chk("the machine kept running", v != 32'd0);

    // ================= configuration error is located =================
    csr_wr(12'h080, 2'd0, 32'h1);
    // 200 beats from beat 200 leaves the buffer
    push(1, 3'd2, mk(3'(P_MTE_IN), 6'd0, 8'h5A,
                     dma_pl(48'h0, 16'h00C8, 1, 200)));
    wait_idle();
    csr_rd(12'h004, 2'd0, v);
    chk("err_task raised for an out-of-range window", v[2] === 1'b1);
    csr_rd(12'h020, 2'd0, v);
    chk("ERR_TAG carries the tag",  v[12:5] === 8'h5A);
    chk("ERR_TAG carries the port", v[4:3]  === 2'd1);
    chk("ERR_TAG carries the pipe", v[2:0]  === 3'(P_MTE_IN));

    // ================= event counter saturation is reported =================
    csr_wr(12'h080, 2'd0, 32'h1);
    for (int i = 0; i < 10; i++)                 // 10 sets, nothing waits
      push(0, 3'd0, mk(3'(P_VEC), 6'h3F, 8'(8'h30 + 8'(i)), '0,
                       '0, 1'b1, 4'd5));
    wait_idle();
    csr_rd(12'h004, 2'd0, v);
    chk("err_evt_ovf reported the swallowed sets", v[1] === 1'b1);
    csr_wr(12'h080, 2'd0, 32'h1);                // clears the counters too

    // ================= queue priority =================
    csr_wr(12'h084, 2'd0, 32'h0000_0080);        // queue 7 is high priority
    // fill low-priority queues first, then one op on the high queue
    for (int i = 0; i < 6; i++)
      push(0, 3'd0, mk(3'(P_VEC), 6'h3F, 8'(8'h40 + 8'(i)), '0));
    for (int i = 0; i < 6; i++)
      push(1, 3'd1, mk(3'(P_VEC), 6'h3F, 8'(8'h50 + 8'(i)), '0));
    pop_log.delete();
    push(2, 3'd7, mk(3'(P_VEC), 6'h3F, 8'h60, '0));
    wait_idle();
    begin
      int first7 = -1;
      for (int i = 0; i < pop_log.size(); i++)
        if (first7 < 0 && pop_log[i] == 3'd7) first7 = i;
      chk("the high-priority queue was popped", first7 >= 0);
      chk("it overtook the backlog", first7 >= 0 && first7 < 3);
    end
    csr_wr(12'h084, 2'd0, 32'h0);

    // ================= queue-scope barrier orders its own queue =========
    csr_wr(12'h080, 2'd0, 32'h1);
    push(0, 3'd0, mk(3'(P_MTE_IN), 6'd0, 8'h70,
                     dma_pl(48'h0, 16'h0030, 1, 8)));
    // a barrier on the same queue may not issue until the load retires
    push(0, 3'd0, mk(3'(P_MTE_OUT), 6'd0, 8'h71,
                     dma_pl(48'hC000, 16'h0030, 1, 8), '0, 1'b0, 4'd0, 1'b1));
    wait_idle();
    csr_rd(12'h004, 2'd0, v);
    chk("barrier run is clean", v[3:0] === 4'd0);
    for (int i = 0; i < 8; i++)
      chk($sformatf("barrier ordered the store, beat %0d", i),
          u_mem.mem[32'h600 + i] === u_mem.mem[i]);

    // ================= Q-Channel =================
    // a request while work is outstanding must be denied, not accepted
    push(0, 3'd0, mk(3'(P_MTE_IN), 6'd0, 8'h80,
                     dma_pl(48'h0, 16'h0040, 1, 16)));
    @(negedge clk) qreqn = 1'b0;
    repeat (3) @(posedge clk);
    chk("busy machine denies quiescence", qdeny === 1'b1 && qacceptn === 1'b1);
    @(negedge clk) qreqn = 1'b1;
    wait_idle();

    @(negedge clk) qreqn = 1'b0;
    repeat (4) @(posedge clk);
    chk("idle machine accepts quiescence", qacceptn === 1'b0 && qdeny === 1'b0);
    chk("qactive is low when quiescent", qactive === 1'b0);

    // while stopped, a submitted descriptor must not be fetched
    push(0, 3'd0, mk(3'(P_MTE_OUT), 6'd0, 8'h81,
                     dma_pl(48'hE000, 16'h0040, 1, 16)));
    repeat (40) @(posedge clk);
    chk("fetch is gated while stopped", u_dut.u_sched.wv === '0);
    chk("the descriptor is still queued", u_dut.u_msgq.all_empty === 1'b0);

    @(negedge clk) qreqn = 1'b1;
    repeat (2) @(posedge clk);
    chk("qacceptn deasserts on release", qacceptn === 1'b1);
    wait_idle();
    for (int i = 0; i < 16; i++)
      chk($sformatf("work resumed after quiescence, beat %0d", i),
          u_mem.mem[32'h700 + i] === u_mem.mem[i]);

    // ================= interrupts =================
    csr_wr(12'h080, 2'd0, 32'h1);              // clear counters and IRQ_STATUS
    csr_wr(12'h02C, 2'd0, 32'h0000_0002);      // enable IRQ_IDLE only
    chk("irq low with nothing pending", irq === 1'b0);
    push(0, 3'd0, mk(3'(P_MTE_IN), 6'd0, 8'h90,
                     dma_pl(48'h0, 16'h0050, 1, 4)));
    // wait for the completion without polling STATUS: the line is the point
    begin
      int guard = 0;
      while (irq !== 1'b1 && guard < 20000) begin
        @(posedge clk);
        guard++;
      end
    end
    chk("IRQ_IDLE raised the line", irq === 1'b1);
    csr_rd(12'h028, 2'd0, v);
    chk("IRQ_STATUS records idle",      v[1] === 1'b1);
    chk("IRQ_STATUS records completion", v[0] === 1'b1);
    csr_wr(12'h028, 2'd0, 32'h0000_0002);      // write 1 to clear IRQ_IDLE
    chk("clearing the enabled source drops the line", irq === 1'b0);
    csr_rd(12'h028, 2'd0, v);
    chk("a masked source stays set", v[0] === 1'b1);
    csr_wr(12'h02C, 2'd0, 32'h0000_0001);      // now enable IRQ_DONE
    chk("enabling a set source raises the line", irq === 1'b1);
    csr_wr(12'h028, 2'd0, 32'hFFFF_FFFF);
    chk("clearing everything drops the line", irq === 1'b0);
    csr_wr(12'h02C, 2'd0, 32'h0);

    // ================= soft reset recovers a hung pipe =================
    csr_wr(12'h080, 2'd0, 32'h1);
    mem_stall = 1'b1;                          // the memory stops answering
    push(0, 3'd0, mk(3'(P_MTE_IN), 6'd0, 8'hA0,
                     dma_pl(48'h0, 16'h0060, 1, 16)));
    // it must hang, and the watchdog must say where
    begin
      int guard = 0;
      forever begin
        csr_rd(12'h004, 2'd0, v);
        if (v[3]) break;                       // err_hang
        guard++;
        if (guard > 20000) begin
          chk("watchdog fired on a stalled memory", 1'b0);
          break;
        end
      end
    end
    chk("err_hang raised", v[3] === 1'b1);
    csr_rd(12'h024, 2'd0, v);
    chk("the snapshot blames MTE_IN", v[P_MTE_IN*4 +: 4] != 4'd0);
    csr_rd(12'h004, 2'd0, v);
    chk("the machine is not idle while hung", v[4] === 1'b0);

    // reset just that pipe
    mem_stall = 1'b0;
    csr_wr(12'h098, 2'd0, 32'(1 << P_MTE_IN));
    begin
      int guard = 0;
      forever begin
        csr_rd(12'h098, 2'd0, v);
        if (v[P_MTE_IN] === 1'b0) break;
        guard++;
        if (guard > 1000) begin
          chk("soft reset completed", 1'b0);
          break;
        end
      end
    end
    csr_rd(12'h004, 2'd0, v);
    chk("the machine is idle again after the reset", v[4] === 1'b1);
    chk("err_hang cleared by the recovery", v[3] === 1'b0);

    // and it still works: a fresh transfer on the reset pipe must complete
    push(0, 3'd0, mk(3'(P_MTE_IN), 6'd0, 8'hA1,
                     dma_pl(48'h0, 16'h0070, 1, 8), '0, 1'b1, 4'd7));
    push(0, 3'd0, mk(3'(P_MTE_OUT), 6'd0, 8'hA2,
                     dma_pl(48'h10000, 16'h0070, 1, 8), 16'h0080));
    wait_idle();
    csr_rd(12'h004, 2'd0, v);
    chk("no errors after recovery", v[3:0] === 4'd0);
    for (int i = 0; i < 8; i++)
      chk($sformatf("pipe works after soft reset, beat %0d", i),
          u_mem.mem[32'h800 + i] === u_mem.mem[i]);

    // ================= crossbar conflict counter =================
    csr_rd(12'h09C, 2'd0, v);
    csr_rd(12'h0A0, 2'd0, v2);
    $display("  xbar conflicts: read %0d cycles, write %0d cycles", v, v2);

    if (errors == 0) $display("TEST PASSED (tb_ctrl)");
    else             $display("TEST FAILED (tb_ctrl): %0d errors", errors);
    $finish;
  end

  initial begin
    #20000000;
    $display("TEST FAILED (tb_ctrl): timeout");
    $finish;
  end
endmodule
