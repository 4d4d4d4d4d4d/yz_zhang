// =====================================================================
// npu_buffer.sv -- one on-chip buffer bank: BUF_D beats x BUS_W bit,
// stored as BUF_D x LINE_W with SECDED per 16-bit lane.
//
// Simple dual port: one read and one write per cycle. Read data is
// registered (1 cycle latency) and CANNOT be back-pressured -- the
// requester must own a landing slot before it is granted. That is the
// read-response credit rule enforced one level up in npu_xbar.
// =====================================================================
`ifndef NPU_BUFFER_SV
`define NPU_BUFFER_SV

module npu_buffer
  import npu_pkg::*;
(
  input  logic                 clk,
  input  logic                 rst_n,

  // write port (lane-granular predicate -> no read-modify-write)
  input  logic                 we,
  input  logic [BUF_AW-1:0]    waddr,
  input  logic [BUS_W-1:0]     wdata,
  input  logic [LANES-1:0]     wmask,

  // ECC error injection, applied on write to lane 0 of the written beat
  input  logic [1:0]           inj,     // 01 = 1 bit (CE), 10 = 2 bits (UE)

  // read port
  input  logic                 re,
  input  logic [BUF_AW-1:0]    raddr,
  output logic                 rvalid,
  output logic [BUS_W-1:0]     rdata,
  output logic [LANES-1:0]     rce,
  output logic [LANES-1:0]     rue
);

  logic [LINE_W-1:0] mem [BUF_D];
  logic [LINE_W-1:0] wline, wline_inj;
  logic [LINE_W-1:0] rline_q;

  npu_ecc_enc u_enc (.data(wdata), .line(wline));

  always_comb begin
    wline_inj = wline;
    unique case (inj)
      2'b01:   wline_inj[0]   = ~wline[0];
      2'b10: begin
               wline_inj[0]   = ~wline[0];
               wline_inj[1]   = ~wline[1];
             end
      default: ;
    endcase
  end

  always_ff @(posedge clk) begin
    if (we)
      for (int l = 0; l < LANES; l++)
        if (wmask[l]) mem[waddr][l*ECC_N +: ECC_N] <= wline_inj[l*ECC_N +: ECC_N];
    if (re) rline_q <= mem[raddr];
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) rvalid <= 1'b0;
    else        rvalid <= re;
  end

  npu_ecc_dec u_dec (.line(rline_q), .data(rdata), .ce(rce), .ue(rue));

endmodule

`endif
