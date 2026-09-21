// =====================================================================
// npu_msgq.sv -- NQ queues x QD entries, NMCU write ports.
//
// * One push and one pop per cycle (single-port storage + RR arbitration
//   on the push side), so the queue array maps to a single SRAM macro.
// * qid comes from the queue the descriptor physically lands in and
//   mcu_id from the ingress port index. Neither is taken from the
//   descriptor, so software cannot forge them. That is what makes the
//   completion route trustworthy and the LOCK owner field meaningful.
// * A full queue back-pressures (push_ready low). Nothing is ever
//   dropped or overwritten.
// * Pop uses two priority levels: any non-empty high-priority queue wins,
//   round-robin inside each level so neither level starves internally.
// =====================================================================
`ifndef NPU_MSGQ_SV
`define NPU_MSGQ_SV

module npu_msgq
  import npu_pkg::*;
(
  input  logic                    clk,
  input  logic                    rst_n,

  // ---- MCU ingress ----
  input  logic [NMCU-1:0]              push_valid,
  input  logic [NMCU-1:0][QIDW-1:0]    push_qid,
  input  logic [NMCU-1:0][DESC_W-1:0]  push_desc,
  output logic [NMCU-1:0]              push_ready,

  // ---- queue priority bitmap (CSR 0x84) ----
  input  logic [NQ-1:0]           qprio,

  // ---- egress to the scheduler ----
  output logic                    pop_valid,
  output logic [DESC_W-1:0]       pop_desc,
  output logic [QIDW-1:0]         pop_qid,
  output logic [MCUW-1:0]         pop_mcu,
  input  logic                    pop_ready,

  // ---- observability ----
  output logic                    stat_full,   // a push was blocked this cycle
  output logic                    all_empty
);

  localparam int QAW = $clog2(QD);

  logic [DESC_W+MCUW-1:0] mem [NQ][QD];
  logic [QAW-1:0]         head [NQ];
  logic [QAW-1:0]         tail [NQ];
  logic [QAW:0]           cnt  [NQ];

  logic [NQ-1:0] q_full, q_empty;
  always_comb
    for (int q = 0; q < NQ; q++) begin
      q_full[q]  = (cnt[q] == (QAW+1)'(QD));
      q_empty[q] = (cnt[q] == '0);
    end
  assign all_empty = &q_empty;

  // ------------------------------------------------ push arbitration
  logic [NMCU-1:0] preq, pgnt;
  always_comb
    for (int m = 0; m < NMCU; m++)
      preq[m] = push_valid[m] && !q_full[push_qid[m]];

  logic do_push;
  assign do_push = |pgnt;

  npu_arb_rr #(.N(NMCU)) u_parb (
    .clk(clk), .rst_n(rst_n), .req(preq), .upd(1'b1), .gnt(pgnt));

  assign push_ready = pgnt;

  // a push was offered but could not land this cycle
  assign stat_full = |(push_valid & ~pgnt);

  logic [QIDW-1:0]    push_q;
  logic [DESC_W-1:0]  push_d;
  logic [MCUW-1:0]    push_m;
  always_comb begin
    push_q = '0; push_d = '0; push_m = '0;
    for (int m = 0; m < NMCU; m++)
      if (pgnt[m]) begin
        push_q = push_qid[m];
        push_d = push_desc[m];
        push_m = MCUW'(m);          // backfilled by hardware
      end
  end

  // ------------------------------------------------ pop arbitration
  logic [NQ-1:0] hi_req, lo_req, hi_gnt, lo_gnt, pop_gnt;
  assign hi_req = ~q_empty &  qprio;
  assign lo_req = ~q_empty & ~qprio;

  logic do_pop;
  assign do_pop = pop_valid && pop_ready;

  npu_arb_rr #(.N(NQ)) u_hiarb (
    .clk(clk), .rst_n(rst_n), .req(hi_req), .upd(do_pop && |hi_req), .gnt(hi_gnt));
  npu_arb_rr #(.N(NQ)) u_loarb (
    .clk(clk), .rst_n(rst_n), .req(lo_req), .upd(do_pop && !(|hi_req)), .gnt(lo_gnt));

  assign pop_gnt   = (|hi_req) ? hi_gnt : lo_gnt;
  assign pop_valid = |pop_gnt;

  logic [QIDW-1:0] pop_q;
  always_comb begin
    pop_q = '0;
    for (int q = 0; q < NQ; q++) if (pop_gnt[q]) pop_q = QIDW'(q);
  end
  assign pop_qid = pop_q;
  assign {pop_mcu, pop_desc} = mem[pop_q][head[pop_q]];

  // ------------------------------------------------ storage update
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int q = 0; q < NQ; q++) begin
        head[q] <= '0; tail[q] <= '0; cnt[q] <= '0;
      end
    end else begin
      if (do_push) begin
        mem[push_q][tail[push_q]] <= {push_m, push_d};
        tail[push_q] <= tail[push_q] + 1'b1;
      end
      if (do_pop) head[pop_q] <= head[pop_q] + 1'b1;

      for (int q = 0; q < NQ; q++) begin
        automatic logic inc = do_push && (push_q == QIDW'(q));
        automatic logic dec = do_pop  && (pop_q  == QIDW'(q));
        if (inc && !dec)      cnt[q] <= cnt[q] + 1'b1;
        else if (!inc && dec) cnt[q] <= cnt[q] - 1'b1;
      end
    end
  end

endmodule

`endif
