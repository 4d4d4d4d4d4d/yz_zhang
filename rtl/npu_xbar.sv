// =====================================================================
// npu_xbar.sv -- read and write crossbars between the execution pipes
// and the NBUF on-chip buffer banks.
//
// Read  requesters (NRD=6): CUBE.A CUBE.B VEC.A VEC.B FIX MTE_OUT
// Write requesters (NWR=4): CUBE VEC FIX MTE_IN
//
// Per bank a round-robin arbiter picks one requester. A requester that
// loses simply holds its request; it is the pipe's own back-pressure.
// Read responses come back one cycle after grant, routed by a registered
// one-hot grant vector -- the bank has no way to stall them.
// =====================================================================
`ifndef NPU_XBAR_SV
`define NPU_XBAR_SV

module npu_xbar
  import npu_pkg::*;
#(
  parameter int NRD = 6,
  parameter int NWR = 4
) (
  input  logic clk,
  input  logic rst_n,

  // ---- read requesters ----
  input  logic [NRD-1:0]              rd_req,
  input  logic [NRD-1:0][GAW-1:0]     rd_addr,
  output logic [NRD-1:0]              rd_gnt,
  output logic [NRD-1:0]              rd_rvalid,
  output logic [NRD-1:0][BUS_W-1:0]   rd_rdata,

  // ---- write requesters ----
  input  logic [NWR-1:0]              wr_req,
  input  logic [NWR-1:0][GAW-1:0]     wr_addr,
  input  logic [NWR-1:0][BUS_W-1:0]   wr_data,
  input  logic [NWR-1:0][LANES-1:0]   wr_mask,
  output logic [NWR-1:0]              wr_gnt,

  // ---- ECC injection + reporting ----
  input  logic [1:0]                  ecc_inj,
  input  logic [BUFIDW-1:0]           ecc_inj_buf,
  output logic                        ecc_ce,
  output logic                        ecc_ue,
  output logic [BUFIDW+BUF_AW-1:0]    ecc_loc
);

  // ------------------------------------------------ per-bank signals
  logic [NBUF-1:0]              b_we, b_re, b_rvalid;
  logic [NBUF-1:0][BUF_AW-1:0]  b_waddr, b_raddr;
  logic [NBUF-1:0][BUS_W-1:0]   b_wdata, b_rdata;
  logic [NBUF-1:0][LANES-1:0]   b_wmask, b_rce, b_rue;
  logic [NBUF-1:0][1:0]         b_inj;

  // ------------------------------------------------ read arbitration
  logic [NBUF-1:0][NRD-1:0] rreq_b, rgnt_b;
  logic [NBUF-1:0][NRD-1:0] rgnt_q;

  always_comb
    for (int b = 0; b < NBUF; b++)
      for (int r = 0; r < NRD; r++)
        rreq_b[b][r] = rd_req[r] && (rd_addr[r][GAW-1:BUF_AW] == BUFIDW'(b));

  for (genvar b = 0; b < NBUF; b++) begin : g_rarb
    npu_arb_rr #(.N(NRD)) u_arb (
      .clk(clk), .rst_n(rst_n), .req(rreq_b[b]), .upd(1'b1), .gnt(rgnt_b[b]));

    always_comb begin
      b_re[b]    = |rgnt_b[b];
      b_raddr[b] = '0;
      for (int r = 0; r < NRD; r++)
        if (rgnt_b[b][r]) b_raddr[b] = rd_addr[r][BUF_AW-1:0];
    end

    always_ff @(posedge clk or negedge rst_n) begin
      if (!rst_n) rgnt_q[b] <= '0;
      else        rgnt_q[b] <= rgnt_b[b];
    end
  end

  always_comb begin
    rd_gnt = '0;
    for (int b = 0; b < NBUF; b++) rd_gnt |= rgnt_b[b];
  end

  // route responses back: exactly one bank can have granted a given
  // requester in a given cycle, so an OR-mux is safe
  always_comb begin
    rd_rvalid = '0;
    rd_rdata  = '0;
    for (int r = 0; r < NRD; r++)
      for (int b = 0; b < NBUF; b++)
        if (rgnt_q[b][r] && b_rvalid[b]) begin
          rd_rvalid[r] = 1'b1;
          rd_rdata[r]  = b_rdata[b];
        end
  end

  // ------------------------------------------------ write arbitration
  logic [NBUF-1:0][NWR-1:0] wreq_b, wgnt_b;

  always_comb
    for (int b = 0; b < NBUF; b++)
      for (int w = 0; w < NWR; w++)
        wreq_b[b][w] = wr_req[w] && (wr_addr[w][GAW-1:BUF_AW] == BUFIDW'(b));

  for (genvar b = 0; b < NBUF; b++) begin : g_warb
    npu_arb_rr #(.N(NWR)) u_arb (
      .clk(clk), .rst_n(rst_n), .req(wreq_b[b]), .upd(1'b1), .gnt(wgnt_b[b]));

    always_comb begin
      b_we[b]    = |wgnt_b[b];
      b_waddr[b] = '0;
      b_wdata[b] = '0;
      b_wmask[b] = '0;
      for (int w = 0; w < NWR; w++)
        if (wgnt_b[b][w]) begin
          b_waddr[b] = wr_addr[w][BUF_AW-1:0];
          b_wdata[b] = wr_data[w];
          b_wmask[b] = wr_mask[w];
        end
      b_inj[b] = (ecc_inj_buf == BUFIDW'(b)) ? ecc_inj : 2'b00;
    end
  end

  always_comb begin
    wr_gnt = '0;
    for (int b = 0; b < NBUF; b++) wr_gnt |= wgnt_b[b];
  end

  // ------------------------------------------------ banks
  for (genvar b = 0; b < NBUF; b++) begin : g_buf
    npu_buffer u_buf (
      .clk(clk), .rst_n(rst_n),
      .we(b_we[b]), .waddr(b_waddr[b]), .wdata(b_wdata[b]), .wmask(b_wmask[b]),
      .inj(b_inj[b]),
      .re(b_re[b]), .raddr(b_raddr[b]),
      .rvalid(b_rvalid[b]), .rdata(b_rdata[b]), .rce(b_rce[b]), .rue(b_rue[b]));
  end

  // ------------------------------------------------ ECC reporting
  // first occurrence latches the location; counters live in the CSR block
  logic [NBUF-1:0] any_ce, any_ue;
  always_comb
    for (int b = 0; b < NBUF; b++) begin
      any_ce[b] = b_rvalid[b] && (|b_rce[b]);
      any_ue[b] = b_rvalid[b] && (|b_rue[b]);
    end

  assign ecc_ce = |any_ce;
  assign ecc_ue = |any_ue;

  always_comb begin
    ecc_loc = '0;
    for (int b = 0; b < NBUF; b++)
      if (any_ce[b] || any_ue[b]) ecc_loc = {BUFIDW'(b), b_raddr[b]};
  end

endmodule

`endif
