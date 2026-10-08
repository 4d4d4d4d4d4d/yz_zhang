// =====================================================================
// npu_qch.sv -- Q-Channel low power quiescence handshake.
//
// The whole point is what counts as "quiescent". It is NOT enough that the
// execution units are idle:
//
//   quiescent = scheduler idle and queues empty
//             && no AXI read transaction outstanding   (AR sent, R not back)
//             && no AXI write transaction outstanding  (AW sent, B not back)
//
// Drop the last two and power goes away while transactions are in flight;
// they never return, the bus hangs, and there is nothing left on chip to
// tell you why.
//
// q_stop gates instruction fetch. It must gate BOTH valid and ready of the
// gated handshake: masking valid alone loses a descriptor that the consumer
// has already accepted, masking ready alone lets the producer re-present one
// that was already taken.
// =====================================================================
`ifndef NPU_QCH_SV
`define NPU_QCH_SV

module npu_qch (
  input  logic clk,
  input  logic rst_n,

  input  logic qreqn,        // 0 =请求进入静止
  output logic qacceptn,     // 0 = accepted
  output logic qdeny,        // 1 = refused
  output logic qactive,      // 1 = work present or in flight

  input  logic sched_idle,
  input  logic queues_empty,
  input  logic ext_rd_outstanding,
  input  logic ext_wr_outstanding,

  output logic q_stop        // gate instruction fetch
);
  typedef enum logic [1:0] {Q_RUN, Q_STOPPED, Q_DENIED} qst_e;
  qst_e qst;

  logic quiescent;
  assign quiescent = sched_idle && queues_empty
                     && !ext_rd_outstanding && !ext_wr_outstanding;

  assign qactive  = !quiescent;
  assign qacceptn = (qst != Q_STOPPED);
  assign qdeny    = (qst == Q_DENIED);
  assign q_stop   = (qst == Q_STOPPED);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      qst <= Q_RUN;
    end else begin
      unique case (qst)
        Q_RUN:     if (!qreqn) qst <= quiescent ? Q_STOPPED : Q_DENIED;
        Q_STOPPED: if (qreqn)  qst <= Q_RUN;
        Q_DENIED:  if (qreqn)  qst <= Q_RUN;
        default:   qst <= Q_RUN;
      endcase
    end
  end
endmodule

`endif
