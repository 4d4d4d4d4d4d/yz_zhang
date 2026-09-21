// =====================================================================
// npu_top.sv -- integration.
//
//  MCU x4 --push--> msgq (8q x 16) --skid--> OpSch --credit--> 5 pipes
//                                      ^                        |
//                                      +------ cpl / event -----+
//          pipes <--> read/write crossbar <--> 4 buffers (ECC)
//          MTE   <--> external memory (AXI4, multi-ID, OOO returns)
//          CSR   <--  AXI4-Lite (counters / errors / locks / ECC inject)
//          Q-Channel   low power quiescence handshake
//
// The skid buffer between msgq and OpSch is load bearing. OpSch's in_ready
// is a function of the entire issue-selection cone (which entries retire
// this cycle); without the skid that cone would reach back through the
// message queue into the MCU write ports.
// =====================================================================
`ifndef NPU_TOP_SV
`define NPU_TOP_SV

module npu_top
  import npu_pkg::*;
(
  input  logic                        clk,
  input  logic                        rst_n,

  // ---- task submission, one port per MCU ----
  input  logic [NMCU-1:0]             push_valid,
  input  logic [NMCU-1:0][QIDW-1:0]   push_qid,
  input  logic [NMCU-1:0][DESC_W-1:0] push_desc,
  output logic [NMCU-1:0]             push_ready,

  // ---- data plane: AXI4 master ----
  output logic                        m_arvalid,
  input  logic                        m_arready,
  output logic [AXI_AW-1:0]           m_araddr,
  output logic [7:0]                  m_arlen,
  output logic [2:0]                  m_arsize,
  output logic [1:0]                  m_arburst,
  output logic [AXI_IDW-1:0]          m_arid,
  input  logic                        m_rvalid,
  output logic                        m_rready,
  input  logic [AXI_DW-1:0]           m_rdata,
  input  logic [AXI_IDW-1:0]          m_rid,
  input  logic                        m_rlast,

  output logic                        m_awvalid,
  input  logic                        m_awready,
  output logic [AXI_AW-1:0]           m_awaddr,
  output logic [7:0]                  m_awlen,
  output logic [2:0]                  m_awsize,
  output logic [1:0]                  m_awburst,
  output logic [AXI_IDW-1:0]          m_awid,
  output logic                        m_wvalid,
  input  logic                        m_wready,
  output logic [AXI_DW-1:0]           m_wdata,
  output logic [AXI_DW/8-1:0]         m_wstrb,
  output logic                        m_wlast,
  input  logic                        m_bvalid,
  output logic                        m_bready,

  // ---- control plane: AXI4-Lite slave ----
  input  logic                        s_awvalid,
  output logic                        s_awready,
  input  logic [LT_AW-1:0]            s_awaddr,
  input  logic [MCUW-1:0]             s_awid,
  input  logic                        s_wvalid,
  output logic                        s_wready,
  input  logic [LT_DW-1:0]            s_wdata,
  input  logic [LT_DW/8-1:0]          s_wstrb,
  output logic                        s_bvalid,
  input  logic                        s_bready,
  output logic [1:0]                  s_bresp,
  input  logic                        s_arvalid,
  output logic                        s_arready,
  input  logic [LT_AW-1:0]            s_araddr,
  input  logic [MCUW-1:0]             s_arid,
  output logic                        s_rvalid,
  input  logic                        s_rready,
  output logic [LT_DW-1:0]            s_rdata,
  output logic [1:0]                  s_rresp,

  // ---- Q-Channel ----
  input  logic                        qreqn,
  output logic                        qacceptn,
  output logic                        qdeny,
  output logic                        qactive
);

  localparam int NRD = 6;   // CUBE.A CUBE.B VEC.A VEC.B FIX MTE_OUT
  localparam int NWR = 4;   // CUBE VEC FIX MTE_IN

  // ================= message queue -> skid -> scheduler =================
  logic               mq_pop_valid, mq_pop_ready;
  logic [DESC_W-1:0]  mq_pop_desc;
  logic [QIDW-1:0]    mq_pop_qid;
  logic [MCUW-1:0]    mq_pop_mcu;
  logic               mq_full_stat, mq_empty;
  logic [NQ-1:0]      qprio;

  npu_msgq u_msgq (
    .clk(clk), .rst_n(rst_n),
    .push_valid(push_valid), .push_qid(push_qid), .push_desc(push_desc),
    .push_ready(push_ready), .qprio(qprio),
    .pop_valid(mq_pop_valid), .pop_desc(mq_pop_desc), .pop_qid(mq_pop_qid),
    .pop_mcu(mq_pop_mcu), .pop_ready(mq_pop_ready),
    .stat_full(mq_full_stat), .all_empty(mq_empty));

  logic q_stop;

  // Instruction fetch gating masks BOTH sides of the handshake. Masking one
  // side re-presents or loses a descriptor that was already taken.
  logic                          sk_s_valid, sk_s_ready;
  logic                          sk_m_valid, sk_m_ready;
  logic [DESC_W+QIDW+MCUW-1:0]   sk_s_data, sk_m_data;

  assign sk_s_valid   = mq_pop_valid && !q_stop;
  assign mq_pop_ready = sk_s_ready   && !q_stop;
  assign sk_s_data    = {mq_pop_mcu, mq_pop_qid, mq_pop_desc};

  npu_skid #(.W(DESC_W + QIDW + MCUW)) u_skid (
    .clk(clk), .rst_n(rst_n),
    .s_valid(sk_s_valid), .s_ready(sk_s_ready), .s_data(sk_s_data),
    .m_valid(sk_m_valid), .m_ready(sk_m_ready), .m_data(sk_m_data));

  // A descriptor parked in the skid buffer is in neither the message queue
  // nor the issue window. Leaving it out of the idle term makes the machine
  // report "done" for the cycle or two it takes to hand over -- software
  // then reads a result that has not been produced, and the Q-Channel would
  // accept a power-down request with work still to do. The global barrier
  // needs the same term for a different reason; see npu_opsched.
  logic fetch_empty;
  assign fetch_empty = mq_empty && !sk_m_valid && !sk_s_valid;

  // ================= scheduler =================
  logic [NEVT-1:0] evt_nz, cons_mask;
  logic            cons_en;
  logic [NPIPE-1:0] iss_valid;
  op_t  [NPIPE-1:0] iss_op;
  logic [NPIPE-1:0] cpl_valid;
  cpl_t [NPIPE-1:0] cpl;
  logic             sched_idle, stat_win_full;
  logic             err_illegal, err_task, err_hang;
  logic [19:0]      hang_snapshot;
  logic [TAG_W+MCUW+PIPEW-1:0] err_tag;
  logic [31:0]      stat_issued;
  logic [NPIPE-1:0][3:0] inflight_pipe;
  logic             clr_stat;

  npu_opsched u_sched (
    .clk(clk), .rst_n(rst_n), .clr_stat(clr_stat),
    .in_valid(sk_m_valid),
    .in_desc(sk_m_data[DESC_W-1:0]),
    .in_qid (sk_m_data[DESC_W +: QIDW]),
    .in_mcu (sk_m_data[DESC_W+QIDW +: MCUW]),
    .in_ready(sk_m_ready), .fetch_empty(fetch_empty),
    .evt_nz(evt_nz), .cons_en(cons_en), .cons_mask(cons_mask),
    .iss_valid(iss_valid), .iss_op(iss_op),
    .cpl_valid(cpl_valid), .cpl(cpl),
    .idle(sched_idle), .stat_issued(stat_issued),
    .stat_win_full(stat_win_full),
    .err_illegal(err_illegal), .err_task(err_task), .err_hang(err_hang),
    .hang_snapshot(hang_snapshot), .err_tag(err_tag),
    .inflight_pipe(inflight_pipe));

  logic [NPIPE-1:0]      set_en;
  logic [NPIPE-1:0][3:0] set_evt;
  logic                  err_evt_ovf;

  always_comb
    for (int p = 0; p < NPIPE; p++) begin
      set_en[p]  = cpl_valid[p] && cpl[p].set_en;
      set_evt[p] = cpl[p].set_evt;
    end

  npu_sem u_sem (
    .clk(clk), .rst_n(rst_n), .clr(clr_stat),
    .cons_en(cons_en), .cons_mask(cons_mask),
    .set_en(set_en), .set_evt(set_evt),
    .nonzero(evt_nz), .ovf(err_evt_ovf));

  // ================= crossbar =================
  logic [NRD-1:0]            rd_req, rd_gnt, rd_rvalid;
  logic [NRD-1:0][GAW-1:0]   rd_addr;
  logic [NRD-1:0][BUS_W-1:0] rd_rdata;
  logic [NWR-1:0]            wr_req, wr_gnt;
  logic [NWR-1:0][GAW-1:0]   wr_addr;
  logic [NWR-1:0][BUS_W-1:0] wr_data;
  logic [NWR-1:0][LANES-1:0] wr_mask;
  logic [1:0]                ecc_inj;
  logic [BUFIDW-1:0]         ecc_inj_buf;
  logic                      ecc_ce, ecc_ue;
  logic [BUFIDW+BUF_AW-1:0]  ecc_loc;

  npu_xbar #(.NRD(NRD), .NWR(NWR)) u_xbar (
    .clk(clk), .rst_n(rst_n),
    .rd_req(rd_req), .rd_addr(rd_addr), .rd_gnt(rd_gnt),
    .rd_rvalid(rd_rvalid), .rd_rdata(rd_rdata),
    .wr_req(wr_req), .wr_addr(wr_addr), .wr_data(wr_data),
    .wr_mask(wr_mask), .wr_gnt(wr_gnt),
    .ecc_inj(ecc_inj), .ecc_inj_buf(ecc_inj_buf),
    .ecc_ce(ecc_ce), .ecc_ue(ecc_ue), .ecc_loc(ecc_loc));

  // ================= execution pipes =================
  logic [NPIPE-1:0] pipe_busy;

  npu_cube u_cube (
    .clk(clk), .rst_n(rst_n),
    .iss_valid(iss_valid[P_CUBE]), .iss_op(iss_op[P_CUBE]),
    .rd_req(rd_req[1:0]), .rd_addr(rd_addr[1:0]), .rd_gnt(rd_gnt[1:0]),
    .rd_rvalid(rd_rvalid[1:0]), .rd_rdata(rd_rdata[1:0]),
    .wr_req(wr_req[0]), .wr_addr(wr_addr[0]), .wr_data(wr_data[0]),
    .wr_mask(wr_mask[0]), .wr_gnt(wr_gnt[0]),
    .cpl_valid(cpl_valid[P_CUBE]), .cpl(cpl[P_CUBE]),
    .busy(pipe_busy[P_CUBE]));

  npu_vec u_vec (
    .clk(clk), .rst_n(rst_n),
    .iss_valid(iss_valid[P_VEC]), .iss_op(iss_op[P_VEC]),
    .rd_req(rd_req[3:2]), .rd_addr(rd_addr[3:2]), .rd_gnt(rd_gnt[3:2]),
    .rd_rvalid(rd_rvalid[3:2]), .rd_rdata(rd_rdata[3:2]),
    .wr_req(wr_req[1]), .wr_addr(wr_addr[1]), .wr_data(wr_data[1]),
    .wr_mask(wr_mask[1]), .wr_gnt(wr_gnt[1]),
    .cpl_valid(cpl_valid[P_VEC]), .cpl(cpl[P_VEC]),
    .busy(pipe_busy[P_VEC]));

  npu_fix u_fix (
    .clk(clk), .rst_n(rst_n),
    .iss_valid(iss_valid[P_FIX]), .iss_op(iss_op[P_FIX]),
    .rd_req(rd_req[4]), .rd_addr(rd_addr[4]), .rd_gnt(rd_gnt[4]),
    .rd_rvalid(rd_rvalid[4]), .rd_rdata(rd_rdata[4]),
    .wr_req(wr_req[2]), .wr_addr(wr_addr[2]), .wr_data(wr_data[2]),
    .wr_mask(wr_mask[2]), .wr_gnt(wr_gnt[2]),
    .cpl_valid(cpl_valid[P_FIX]), .cpl(cpl[P_FIX]),
    .busy(pipe_busy[P_FIX]));

  logic mte_in_outst, mte_out_outst;

  npu_mte_in u_mte_in (
    .clk(clk), .rst_n(rst_n),
    .iss_valid(iss_valid[P_MTE_IN]), .iss_op(iss_op[P_MTE_IN]),
    .wr_req(wr_req[3]), .wr_addr(wr_addr[3]), .wr_data(wr_data[3]),
    .wr_mask(wr_mask[3]), .wr_gnt(wr_gnt[3]),
    .arvalid(m_arvalid), .arready(m_arready), .araddr(m_araddr),
    .arlen(m_arlen), .arsize(m_arsize), .arburst(m_arburst), .arid(m_arid),
    .rvalid(m_rvalid), .rready(m_rready), .rdata(m_rdata),
    .rid(m_rid), .rlast(m_rlast),
    .cpl_valid(cpl_valid[P_MTE_IN]), .cpl(cpl[P_MTE_IN]),
    .busy(pipe_busy[P_MTE_IN]), .outstanding(mte_in_outst));

  npu_mte_out u_mte_out (
    .clk(clk), .rst_n(rst_n),
    .iss_valid(iss_valid[P_MTE_OUT]), .iss_op(iss_op[P_MTE_OUT]),
    .rd_req(rd_req[5]), .rd_addr(rd_addr[5]), .rd_gnt(rd_gnt[5]),
    .rd_rvalid(rd_rvalid[5]), .rd_rdata(rd_rdata[5]),
    .awvalid(m_awvalid), .awready(m_awready), .awaddr(m_awaddr),
    .awlen(m_awlen), .awsize(m_awsize), .awburst(m_awburst), .awid(m_awid),
    .wvalid(m_wvalid), .wready(m_wready), .wdata(m_wdata),
    .wstrb(m_wstrb), .wlast(m_wlast),
    .bvalid(m_bvalid), .bready(m_bready),
    .cpl_valid(cpl_valid[P_MTE_OUT]), .cpl(cpl[P_MTE_OUT]),
    .busy(pipe_busy[P_MTE_OUT]), .outstanding(mte_out_outst));

  // ================= CSR =================
  npu_csr u_csr (
    .clk(clk), .rst_n(rst_n),
    .awvalid(s_awvalid), .awready(s_awready), .awaddr(s_awaddr), .awid(s_awid),
    .wvalid(s_wvalid), .wready(s_wready), .wdata(s_wdata), .wstrb(s_wstrb),
    .bvalid(s_bvalid), .bready(s_bready), .bresp(s_bresp),
    .arvalid(s_arvalid), .arready(s_arready), .araddr(s_araddr), .arid(s_arid),
    .rvalid(s_rvalid), .rready(s_rready), .rdata(s_rdata), .rresp(s_rresp),
    .idle(sched_idle && fetch_empty),
    .err_illegal(err_illegal), .err_task(err_task), .err_hang(err_hang),
    .err_evt_ovf(err_evt_ovf), .hang_snapshot(hang_snapshot),
    .err_tag(err_tag), .stat_issued(stat_issued),
    .stat_win_full(stat_win_full), .stat_mq_full(mq_full_stat),
    .ext_rd_busy(mte_in_outst), .ext_wr_busy(mte_out_outst),
    .pipe_busy(pipe_busy),
    .ecc_ce(ecc_ce), .ecc_ue(ecc_ue), .ecc_loc(ecc_loc),
    .clr_stat(clr_stat), .qprio(qprio),
    .ecc_inj(ecc_inj), .ecc_inj_buf(ecc_inj_buf));

  // ================= Q-Channel =================
  npu_qch u_qch (
    .clk(clk), .rst_n(rst_n),
    .qreqn(qreqn), .qacceptn(qacceptn), .qdeny(qdeny), .qactive(qactive),
    .sched_idle(sched_idle), .queues_empty(fetch_empty),
    .ext_rd_outstanding(mte_in_outst), .ext_wr_outstanding(mte_out_outst),
    .q_stop(q_stop));

  // ================= protocol checkers (simulation only) =================
  npu_check #(.W(DESC_W + QIDW + MCUW), .NAME("msgq->skid")) u_chk_mq (
    .clk(clk), .rst_n(rst_n),
    .valid(sk_s_valid), .ready(sk_s_ready), .data(sk_s_data));
  npu_check #(.W(DESC_W + QIDW + MCUW), .NAME("skid->sched")) u_chk_sk (
    .clk(clk), .rst_n(rst_n),
    .valid(sk_m_valid), .ready(sk_m_ready), .data(sk_m_data));
  npu_check #(.W(AXI_AW + 8), .NAME("axi-ar")) u_chk_ar (
    .clk(clk), .rst_n(rst_n),
    .valid(m_arvalid), .ready(m_arready), .data({m_araddr, m_arlen}));
  npu_check #(.W(AXI_AW + 8), .NAME("axi-aw")) u_chk_aw (
    .clk(clk), .rst_n(rst_n),
    .valid(m_awvalid), .ready(m_awready), .data({m_awaddr, m_awlen}));
  npu_check #(.W(AXI_DW + 1), .NAME("axi-w")) u_chk_w (
    .clk(clk), .rst_n(rst_n),
    .valid(m_wvalid), .ready(m_wready), .data({m_wdata, m_wlast}));

`ifndef SYNTHESIS
  // Credits must never let a pipe be issued more work than it can hold.
  always_ff @(posedge clk)
    if (rst_n)
      for (int p = 0; p < NPIPE; p++)
        if (inflight_pipe[p] > 4'(CREDIT)) begin
          $display("%%Error: pipe %0d in-flight %0d exceeds credit %0d",
                   p, inflight_pipe[p], CREDIT);
          $stop;
        end
`endif

endmodule

`endif
