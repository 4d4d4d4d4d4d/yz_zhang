// =====================================================================
// npu_fix.sv -- 16x16 tile transpose with ping-pong tiles.
//
// Fill one tile while draining the other, so a long run of tiles moves at
// one beat per cycle in each direction. The transpose exists because the
// two layouts the machine needs are incompatible: CUBE wants K-contiguous
// operands (SEG layout) and a VEC row reduction produces a row-contiguous
// vector (ROW layout). The compiler decides where the boundary falls; this
// unit is what makes crossing it cost one pass instead of a gather.
// =====================================================================
`ifndef NPU_FIX_SV
`define NPU_FIX_SV

module npu_fix
  import npu_pkg::*;
(
  input  logic             clk,
  input  logic             rst_n,

  input  logic             iss_valid,
  input  op_t              iss_op,

  output logic             rd_req,
  output logic [GAW-1:0]   rd_addr,
  input  logic             rd_gnt,
  input  logic             rd_rvalid,
  input  logic [BUS_W-1:0] rd_rdata,

  output logic             wr_req,
  output logic [GAW-1:0]   wr_addr,
  output logic [BUS_W-1:0] wr_data,
  output logic [LANES-1:0] wr_mask,
  input  logic             wr_gnt,

  output logic             cpl_valid,
  output cpl_t             cpl,
  output logic             busy
);

  localparam int RDEPTH = 4;

  logic q_pop, q_empty, q_full_unused;
  logic [$bits(op_t)-1:0] q_dat;
  logic [$clog2(CREDIT+1)-1:0] q_cnt;

  npu_fifo #(.W($bits(op_t)), .D(CREDIT)) u_iq (
    .clk(clk), .rst_n(rst_n),
    .push(iss_valid), .wdata(iss_op), .full(q_full_unused),
    .pop(q_pop), .rdata(q_dat), .empty(q_empty), .count(q_cnt));

  op_t  nq_op;  assign nq_op  = op_t'(q_dat);
  fix_t nq_cfg; assign nq_cfg = fix_t'(nq_op.pl);

  op_t  cur;
  fix_t cfg;    assign cfg = fix_t'(cur.pl);

  typedef enum logic [1:0] {S_IDLE, S_RUN, S_CPL} st_e;
  st_e st;

  logic        err_q;
  logic [15:0] rtile, wtile;      // tiles requested / tiles written
  logic [4:0]  rbeat, wbeat;      // beat within the current tile
  logic        rsel,  wsel;       // ping-pong select
  logic [1:0]  tfull;

  logic [LANES-1:0][BUS_W-1:0] tile [2];

  // ---- read side ----
  logic f_push, f_pop, f_empty, f_full;
  logic [BUS_W-1:0] f_dat;
  logic [$clog2(RDEPTH+1)-1:0] f_cnt;
  logic outst;

  npu_fifo #(.W(BUS_W), .D(RDEPTH)) u_f (
    .clk(clk), .rst_n(rst_n),
    .push(f_push), .wdata(rd_rdata), .full(f_full),
    .pop(f_pop), .rdata(f_dat), .empty(f_empty), .count(f_cnt));
  assign f_push = rd_rvalid;

  logic can_req;
  assign can_req = ({1'b0, f_cnt} + {{$clog2(RDEPTH+1){1'b0}}, outst})
                   < ($clog2(RDEPTH+1)+1)'(RDEPTH);

  // request only while the tile being filled is not already full
  assign rd_req  = (st == S_RUN) && !err_q && (rtile < cfg.tiles)
                   && !tfull[rsel] && can_req;
  assign rd_addr = GAW'(16'(cfg.src_a) + rtile * cfg.s_stride + 16'(rbeat));

  logic fill;
  assign fill  = (st == S_RUN) && !f_empty && !tfull[rsel];
  assign f_pop = fill;

  // ---- write side: row w of the output tile is column w of the input ----
  logic [BUS_W-1:0] tr_beat;
  always_comb
    for (int l = 0; l < LANES; l++)
      tr_beat[l*ELEM_W +: ELEM_W] = tile[wsel][l][wbeat[3:0]*ELEM_W +: ELEM_W];

  assign wr_req  = (st == S_RUN) && !err_q && tfull[wsel];
  assign wr_addr = GAW'(16'(cfg.dst) + wtile * cfg.d_stride + 16'(wbeat));
  assign wr_data = tr_beat;
  assign wr_mask = '1;

  logic drain;
  assign drain = wr_req && wr_gnt;

  // ---- config check ----
  logic cfg_err, is_nop;
  always_comb begin
    automatic op_t  o = nq_op;
    automatic fix_t c = nq_cfg;
    is_nop  = (o.hdr.opc == OPC_NOP);
    cfg_err = 1'b0;
    if (!is_nop) begin
      if (o.hdr.opc != F_TRANS)                            cfg_err = 1'b1;
      if (c.tiles == 16'd0)                                cfg_err = 1'b1;
      // a tile spans LANES consecutive beats from each tile base
      if (addr_ovf(c.src_a, (c.tiles - 16'd1) * c.s_stride + 16'(LANES), 16'd1))
                                                           cfg_err = 1'b1;
      if (addr_ovf(c.dst,   (c.tiles - 16'd1) * c.d_stride + 16'(LANES), 16'd1))
                                                           cfg_err = 1'b1;
    end
  end

  assign busy      = (st != S_IDLE) || !q_empty;
  assign cpl_valid = (st == S_CPL);
  always_comb begin
    cpl.tag     = cur.hdr.tag;
    cpl.mcu     = cur.mcu;
    cpl.qid     = cur.qid;
    cpl.set_evt = cur.hdr.set_evt;
    cpl.set_en  = cur.hdr.set_en;
    cpl.err     = err_q;
  end
  assign q_pop = (st == S_IDLE) && !q_empty;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      st <= S_IDLE;
      err_q <= 1'b0; cur <= '0;
      rtile <= '0; wtile <= '0; rbeat <= '0; wbeat <= '0;
      rsel <= 1'b0; wsel <= 1'b0; tfull <= '0; outst <= 1'b0;
      for (int t = 0; t < 2; t++)
        for (int l = 0; l < LANES; l++) tile[t][l] <= '0;
    end else begin
      outst <= rd_req && rd_gnt;

      unique case (st)
        S_IDLE: if (!q_empty) begin
          cur   <= nq_op;
          err_q <= cfg_err;
          rtile <= '0; wtile <= '0; rbeat <= '0; wbeat <= '0;
          rsel  <= 1'b0; wsel <= 1'b0; tfull <= '0;
          st    <= (cfg_err || (nq_op.hdr.opc == OPC_NOP)) ? S_CPL : S_RUN;
        end

        S_RUN: begin
          if (rd_req && rd_gnt) begin
            if (rbeat == 5'(LANES - 1)) begin
              rbeat <= '0;
              rtile <= rtile + 1'b1;
            end else begin
              rbeat <= rbeat + 1'b1;
            end
          end

          if (fill) begin
            tile[rsel][f_cnt_row] <= f_dat;
            if (fill_last) begin
              tfull[rsel] <= 1'b1;
              rsel        <= ~rsel;
            end
          end

`ifdef NPU_DEBUG
          if (drain)
            $display("[fix] t=%0t write addr=%03h beat=%0d data=%064h",
                     $time, wr_addr, wbeat, wr_data);
`endif
          if (drain) begin
            if (wbeat == 5'(LANES - 1)) begin
              wbeat       <= '0;
              tfull[wsel] <= 1'b0;
              wsel        <= ~wsel;
              if (wtile + 16'd1 == cfg.tiles) st <= S_CPL;
              else                            wtile <= wtile + 1'b1;
            end else begin
              wbeat <= wbeat + 1'b1;
            end
          end
        end

        S_CPL: st <= S_IDLE;
        default: st <= S_IDLE;
      endcase
    end
  end

  // row index inside the tile currently being filled
  logic [4:0] frow;
  logic       fill_last;
  logic [3:0] f_cnt_row;
  assign f_cnt_row = frow[3:0];
  assign fill_last = (frow == 5'(LANES - 1));

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)                       frow <= '0;
    else if (st == S_IDLE)            frow <= '0;
    else if (fill)                    frow <= fill_last ? 5'd0 : frow + 1'b1;
  end

endmodule

`endif
