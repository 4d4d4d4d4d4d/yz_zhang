// =====================================================================
// npu_mte.sv -- memory transfer engines and their shared address
// generator.
//
// npu_agu walks a 2-D window with an optional intra-row stride and emits
// AXI bursts. The intra-row stride is what lets a strided gather be a
// single descriptor instead of a rearrangement pass; on the encoder layer
// it moved rearrangement from 58% of all ops down to 4%.
//
// Out-of-order R returns need no reorder buffer. Each in-flight burst owns
// an AXI ID and a destination beat address; an arriving R beat is tagged
// with its own destination before it is queued, so interleaved IDs simply
// land in different places. What IS required is that a landing slot exists
// before AR goes out -- 'reserved' below is that outstanding credit.
//
// The write engine uses a single AXI ID. AXI4 forbids interleaving W
// bursts, and W must follow AW order, so a single ID costs nothing here
// and removes a whole class of ordering bugs.
// =====================================================================
`ifndef NPU_MTE_SV
`define NPU_MTE_SV

// ---------------------------------------------------------------------
// 2-D strided burst generator
// ---------------------------------------------------------------------
module npu_agu
  import npu_pkg::*;
(
  input  logic        clk,
  input  logic        rst_n,
  input  logic        start,
  input  mte_t        cfg,
  input  logic        next,        // consume the presented burst

  output logic        v,
  output logic [31:0] ext_beat,    // external address in beats
  output logic [GAW-1:0] buf_addr,
  output logic [8:0]  len          // 1 .. MAX_BURST
);
  logic [15:0] r, c, g, w;
  logic        active;

  logic [15:0] icnt, istr;
  assign icnt = (cfg.in_cnt == 16'd0) ? cfg.cols : cfg.in_cnt;
  assign istr = (cfg.in_cnt == 16'd0) ? cfg.cols : cfg.in_stride;

  logic [15:0] run, rem;
  assign run = icnt - w;                    // to the end of this group
  assign rem = cfg.cols - c;                // to the end of this row

  always_comb begin
    automatic logic [15:0] l;
    l = (run < rem) ? run : rem;
    if (l > 16'(MAX_BURST)) l = 16'(MAX_BURST);
    len = 9'(l);
  end

  assign v = active;

  logic [31:0] ext_base;
  assign ext_base = cfg.ext_addr[36:5];     // byte address -> beat index (32 B)
  assign buf_addr = GAW'(16'(cfg.buf_addr) + r * cfg.buf_rstride + c);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      r <= '0; c <= '0; g <= '0; w <= '0; active <= 1'b0;
    end else if (start) begin
      r <= '0; c <= '0; g <= '0; w <= '0; active <= 1'b1;
    end else if (active && next) begin
      if (c + 16'(len) >= cfg.cols) begin   // row finished
        c <= '0; g <= '0; w <= '0;
        if (r + 16'd1 == cfg.rows) active <= 1'b0;
        else                       r <= r + 16'd1;
      end else begin
        c <= c + 16'(len);
        if (w + 16'(len) == icnt) begin
          w <= '0;
          g <= g + 16'd1;
        end else begin
          w <= w + 16'(len);
        end
      end
    end
  end

  // external beat index of the first beat of this burst
  assign ext_beat = ext_base + 32'(r) * cfg.ext_rstride
                             + 32'(g) * 32'(istr) + 32'(w);
endmodule

// ---------------------------------------------------------------------
// MTE_IN : external memory -> on-chip buffer
// ---------------------------------------------------------------------
module npu_mte_in
  import npu_pkg::*;
(
  input  logic                 clk,
  input  logic                 rst_n,

  input  logic                 iss_valid,
  input  op_t                  iss_op,

  output logic                 wr_req,
  output logic [GAW-1:0]       wr_addr,
  output logic [BUS_W-1:0]     wr_data,
  output logic [LANES-1:0]     wr_mask,
  input  logic                 wr_gnt,

  // AXI4 read
  output logic                 arvalid,
  input  logic                 arready,
  output logic [AXI_AW-1:0]    araddr,
  output logic [7:0]           arlen,
  output logic [2:0]           arsize,
  output logic [1:0]           arburst,
  output logic [AXI_IDW-1:0]   arid,
  input  logic                 rvalid,
  output logic                 rready,
  input  logic [AXI_DW-1:0]    rdata,
  input  logic [AXI_IDW-1:0]   rid,
  input  logic                 rlast,

  output logic                 cpl_valid,
  output cpl_t                 cpl,
  output logic                 busy,
  output logic                 outstanding   // AR issued but R not complete
);
  // Sized so the landing FIFO is never the binding constraint: what limits
  // how much latency can be hidden should be burst length times outstanding
  // depth, not an arbitrary buffer.
  localparam int FD  = NID * MAX_BURST;
  localparam int FCW = $clog2(FD + 1);

  logic q_pop, q_empty, q_full_unused;
  logic [$bits(op_t)-1:0] q_dat;
  logic [$clog2(CREDIT+1)-1:0] q_cnt;

  npu_fifo #(.W($bits(op_t)), .D(CREDIT)) u_iq (
    .clk(clk), .rst_n(rst_n),
    .push(iss_valid), .wdata(iss_op), .full(q_full_unused),
    .pop(q_pop), .rdata(q_dat), .empty(q_empty), .count(q_cnt));

  op_t  nq_op;  assign nq_op  = op_t'(q_dat);
  mte_t nq_cfg; assign nq_cfg = mte_t'(nq_op.pl);
  op_t  cur;
  mte_t cfg;    assign cfg = mte_t'(cur.pl);

  typedef enum logic [1:0] {S_IDLE, S_RUN, S_DRAIN, S_CPL} st_e;
  st_e st;
  logic err_q;

  // ---- address generation ----
  logic        agu_start, agu_v, agu_next;
  logic [31:0] agu_ext;
  logic [GAW-1:0] agu_buf;
  logic [8:0]  agu_len;

  npu_agu u_agu (
    .clk(clk), .rst_n(rst_n), .start(agu_start), .cfg(cfg), .next(agu_next),
    .v(agu_v), .ext_beat(agu_ext), .buf_addr(agu_buf), .len(agu_len));

  // ---- per-ID burst bookkeeping ----
  logic [NID-1:0]            id_busy;
  logic [NID-1:0][GAW-1:0]   id_base;
  logic [NID-1:0][8:0]       id_cnt;
  logic [AXI_IDW-1:0]        alloc_id;
  logic                      id_free;

  always_comb begin
    id_free  = 1'b0;
    alloc_id = '0;
    for (int i = NID - 1; i >= 0; i--)
      if (!id_busy[i]) begin
        id_free  = 1'b1;
        alloc_id = AXI_IDW'(i);
      end
  end

  // ---- landing FIFO: {dest, data} ----
  logic            fpush, fpop, fempty, ffull;
  logic [GAW+BUS_W-1:0] fwd, frd;
  logic [FCW-1:0]  fcnt;
  logic [FCW-1:0]  reserved;

  npu_fifo #(.W(GAW + BUS_W), .D(FD)) u_rf (
    .clk(clk), .rst_n(rst_n),
    .push(fpush), .wdata(fwd), .full(ffull),
    .pop(fpop), .rdata(frd), .empty(fempty), .count(fcnt));

  logic room;
  assign room = ({1'b0, fcnt} + {1'b0, reserved} + (FCW+1)'(agu_len))
                <= (FCW+1)'(FD);

  assign arvalid = (st == S_RUN) && agu_v && !err_q && id_free && room;
  assign araddr  = AXI_AW'({agu_ext, 5'd0});        // beats -> bytes
  assign arlen   = 8'(agu_len - 9'd1);
  assign arsize  = 3'd5;                            // 32 bytes per beat
  assign arburst = 2'b01;                           // INCR
  assign arid    = alloc_id;
  assign agu_next = arvalid && arready;

  assign rready = !ffull;
  assign fpush  = rvalid && rready;
  assign fwd    = {GAW'(id_base[rid] + GAW'(id_cnt[rid])), rdata};

  // ---- buffer writer ----
  assign wr_req  = !fempty;
  assign wr_addr = frd[GAW+BUS_W-1 -: GAW];
  assign wr_data = frd[BUS_W-1:0];
  assign wr_mask = '1;
  assign fpop    = wr_req && wr_gnt;

  assign outstanding = (|id_busy) || !fempty;

  // ---- config check ----
  logic cfg_err, is_nop;
  always_comb begin
    automatic op_t  o = nq_op;
    automatic mte_t c = nq_cfg;
    is_nop  = (o.hdr.opc == OPC_NOP);
    cfg_err = 1'b0;
    if (!is_nop) begin
      if (o.hdr.opc != M_XFER)                   cfg_err = 1'b1;
      if (c.rows == 16'd0 || c.cols == 16'd0)    cfg_err = 1'b1;
      if (c.in_cnt != 16'd0 && (c.cols % c.in_cnt) != 16'd0) cfg_err = 1'b1;
      if (addr_ovf(c.buf_addr,
                   (c.rows - 16'd1) * c.buf_rstride + c.cols, 16'd1))
                                                 cfg_err = 1'b1;
      if (c.ext_addr[4:0] != 5'd0)               cfg_err = 1'b1;  // beat aligned
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
      st <= S_IDLE; err_q <= 1'b0; cur <= '0;
      agu_start <= 1'b0; reserved <= '0;
      id_busy <= '0;
      for (int i = 0; i < NID; i++) begin
        id_base[i] <= '0;
        id_cnt[i]  <= '0;
      end
    end else begin
      agu_start <= 1'b0;

      unique case (st)
        S_IDLE: if (!q_empty) begin
          cur   <= nq_op;
          err_q <= cfg_err;
          if (cfg_err || (nq_op.hdr.opc == OPC_NOP)) st <= S_CPL;
          else begin
            st        <= S_RUN;
            agu_start <= 1'b1;
          end
        end
        S_RUN:   if (!agu_v && !agu_start) st <= S_DRAIN;
        S_DRAIN: if (!outstanding)         st <= S_CPL;
        S_CPL:   st <= S_IDLE;
        default: st <= S_IDLE;
      endcase

      // allocate on AR, release on RLAST
      if (arvalid && arready) begin
        id_busy[alloc_id] <= 1'b1;
        id_base[alloc_id] <= agu_buf;
        id_cnt[alloc_id]  <= '0;
      end
      if (rvalid && rready) begin
        id_cnt[rid] <= id_cnt[rid] + 9'd1;
        if (rlast) id_busy[rid] <= 1'b0;
      end

      // outstanding credit: reserve on AR, release as beats land
      case ({arvalid && arready, rvalid && rready})
        2'b10: reserved <= reserved + FCW'(agu_len);
        2'b01: reserved <= reserved - 1'b1;
        2'b11: reserved <= reserved + FCW'(agu_len) - 1'b1;
        default: ;
      endcase
    end
  end
endmodule

// ---------------------------------------------------------------------
// MTE_OUT : on-chip buffer -> external memory
// ---------------------------------------------------------------------
module npu_mte_out
  import npu_pkg::*;
(
  input  logic                 clk,
  input  logic                 rst_n,

  input  logic                 iss_valid,
  input  op_t                  iss_op,

  output logic                 rd_req,
  output logic [GAW-1:0]       rd_addr,
  input  logic                 rd_gnt,
  input  logic                 rd_rvalid,
  input  logic [BUS_W-1:0]     rd_rdata,

  // AXI4 write
  output logic                 awvalid,
  input  logic                 awready,
  output logic [AXI_AW-1:0]    awaddr,
  output logic [7:0]           awlen,
  output logic [2:0]           awsize,
  output logic [1:0]           awburst,
  output logic [AXI_IDW-1:0]   awid,
  output logic                 wvalid,
  input  logic                 wready,
  output logic [AXI_DW-1:0]    wdata,
  output logic [AXI_DW/8-1:0]  wstrb,
  output logic                 wlast,
  input  logic                 bvalid,
  output logic                 bready,

  output logic                 cpl_valid,
  output cpl_t                 cpl,
  output logic                 busy,
  output logic                 outstanding
);
  localparam int FD  = NID * MAX_BURST;
  localparam int FCW = $clog2(FD + 1);

  logic q_pop, q_empty, q_full_unused;
  logic [$bits(op_t)-1:0] q_dat;
  logic [$clog2(CREDIT+1)-1:0] q_cnt;

  npu_fifo #(.W($bits(op_t)), .D(CREDIT)) u_iq (
    .clk(clk), .rst_n(rst_n),
    .push(iss_valid), .wdata(iss_op), .full(q_full_unused),
    .pop(q_pop), .rdata(q_dat), .empty(q_empty), .count(q_cnt));

  op_t  nq_op;  assign nq_op  = op_t'(q_dat);
  mte_t nq_cfg; assign nq_cfg = mte_t'(nq_op.pl);
  op_t  cur;
  mte_t cfg;    assign cfg = mte_t'(cur.pl);

  typedef enum logic [1:0] {S_IDLE, S_RUN, S_DRAIN, S_CPL} st_e;
  st_e st;
  logic err_q;

  logic        agu_start, agu_v, agu_next;
  logic [31:0] agu_ext;
  logic [GAW-1:0] agu_buf;
  logic [8:0]  agu_len;

  npu_agu u_agu (
    .clk(clk), .rst_n(rst_n), .start(agu_start), .cfg(cfg), .next(agu_next),
    .v(agu_v), .ext_beat(agu_ext), .buf_addr(agu_buf), .len(agu_len));

  // ---- data FIFO fed by buffer reads, drained by the W channel ----
  logic            fpush, fpop, fempty;
  /* verilator lint_off UNUSEDSIGNAL */
  logic            ffull;              // cannot assert: guarded by can_rd credit
  /* verilator lint_on UNUSEDSIGNAL */
  logic [BUS_W-1:0] frd;
  logic [FCW-1:0]  fcnt;
  logic [FCW-1:0]  reserved;
  logic            rd_outst;

  npu_fifo #(.W(BUS_W), .D(FD)) u_wf (
    .clk(clk), .rst_n(rst_n),
    .push(fpush), .wdata(rd_rdata), .full(ffull),
    .pop(fpop), .rdata(frd), .empty(fempty), .count(fcnt));
  assign fpush = rd_rvalid;

  // ---- burst length FIFO so the W driver knows where WLAST goes ----
  logic            lpush, lpop, lempty, lfull;
  logic [8:0]      lrd;
  /* verilator lint_off UNUSEDSIGNAL */
  logic [$clog2(NID*2+1)-1:0] lcnt;    // depth is bounded by lfull, not by count
  /* verilator lint_on UNUSEDSIGNAL */

  npu_fifo #(.W(9), .D(NID*2)) u_lf (
    .clk(clk), .rst_n(rst_n),
    .push(lpush), .wdata(agu_len), .full(lfull),
    .pop(lpop), .rdata(lrd), .empty(lempty), .count(lcnt));

  // ---- burst issue: AW once, then len buffer reads ----
  logic [8:0]      rd_left;
  logic [GAW-1:0]  rd_ptr;
  logic            aw_pending;

  // A burst may start only when its whole payload has a reserved slot, the
  // length queue can record it, the previous AW has been accepted and the
  // previous burst's buffer reads have all been issued -- the data FIFO is
  // in burst order and AXI4 forbids interleaving W bursts.
  logic room, accept;
  assign room   = ({1'b0, fcnt} + {1'b0, reserved} + (FCW+1)'(agu_len))
                  <= (FCW+1)'(FD);
  assign accept = (st == S_RUN) && agu_v && !err_q && room && !lfull
                  && !aw_pending && (rd_left == 9'd0);

  assign awvalid = aw_pending;
  assign awaddr  = AXI_AW'({aw_ext, 5'd0});
  assign awlen   = 8'(aw_len - 9'd1);
  assign awsize  = 3'd5;
  assign awburst = 2'b01;
  assign awid    = '0;                        // single ID: AXI4 forbids W interleave

  logic [31:0] aw_ext;
  logic [8:0]  aw_len;

  assign rd_req  = (rd_left != 9'd0) && can_rd;
  assign rd_addr = rd_ptr;

  logic can_rd;
  assign can_rd = ({1'b0, fcnt} + {{FCW{1'b0}}, rd_outst}) < (FCW+1)'(FD);

  assign agu_next = accept;
  assign lpush    = accept;

  // ---- W channel ----
  logic [8:0] w_left;
  assign wvalid = !fempty && (w_left != 9'd0);
  assign wdata  = frd;
  assign wstrb  = '1;
  assign wlast  = (w_left == 9'd1);
  assign fpop   = wvalid && wready;
  assign lpop   = wvalid && wready && wlast;

  logic [7:0] b_out;
  assign bready = 1'b1;
  assign outstanding = (b_out != 8'd0) || !fempty || (rd_left != 9'd0);

  // ---- config check ----
  logic cfg_err, is_nop;
  always_comb begin
    automatic op_t  o = nq_op;
    automatic mte_t c = nq_cfg;
    is_nop  = (o.hdr.opc == OPC_NOP);
    cfg_err = 1'b0;
    if (!is_nop) begin
      if (o.hdr.opc != M_XFER)                   cfg_err = 1'b1;
      if (c.rows == 16'd0 || c.cols == 16'd0)    cfg_err = 1'b1;
      if (c.in_cnt != 16'd0 && (c.cols % c.in_cnt) != 16'd0) cfg_err = 1'b1;
      if (addr_ovf(c.buf_addr,
                   (c.rows - 16'd1) * c.buf_rstride + c.cols, 16'd1))
                                                 cfg_err = 1'b1;
      if (c.ext_addr[4:0] != 5'd0)               cfg_err = 1'b1;
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
      st <= S_IDLE; err_q <= 1'b0; cur <= '0;
      agu_start <= 1'b0; reserved <= '0; rd_outst <= 1'b0;
      rd_left <= '0; rd_ptr <= '0; w_left <= '0; b_out <= '0;
      aw_pending <= 1'b0; aw_ext <= '0; aw_len <= '0;
    end else begin
      agu_start <= 1'b0;
      rd_outst  <= rd_req && rd_gnt;

      unique case (st)
        S_IDLE: if (!q_empty) begin
          cur   <= nq_op;
          err_q <= cfg_err;
          if (cfg_err || (nq_op.hdr.opc == OPC_NOP)) st <= S_CPL;
          else begin
            st        <= S_RUN;
            agu_start <= 1'b1;
          end
        end
        S_RUN:   if (!agu_v && !agu_start && (rd_left == 9'd0)) st <= S_DRAIN;
        S_DRAIN: if (!outstanding) st <= S_CPL;
        S_CPL:   st <= S_IDLE;
        default: st <= S_IDLE;
      endcase

      // start a burst
      if (accept) begin
        aw_pending <= 1'b1;
        aw_ext     <= agu_ext;
        aw_len     <= agu_len;
        rd_left    <= agu_len;
        rd_ptr     <= agu_buf;
      end

      // outstanding credit: reserve a slot per beat at burst start, release
      // it as the beat actually lands in the data FIFO
      case ({accept, rd_rvalid})
        2'b10:   reserved <= reserved + FCW'(agu_len);
        2'b01:   reserved <= reserved - 1'b1;
        2'b11:   reserved <= reserved + FCW'(agu_len) - 1'b1;
        default: ;
      endcase
      if (awvalid && awready) aw_pending <= 1'b0;

`ifdef NPU_DEBUG
      if (accept)
        $display("[mteo] t=%0t burst ext=%0h buf=%03h len=%0d",
                 $time, agu_ext, agu_buf, agu_len);
      if (rd_rvalid)
        $display("[mteo] t=%0t rdata=%064h", $time, rd_rdata);
      if (wvalid && wready)
        $display("[mteo] t=%0t W data=%064h last=%0d", $time, wdata, wlast);
`endif
      // buffer reads feed the data FIFO in burst order
      if (rd_req && rd_gnt) begin
        rd_left <= rd_left - 9'd1;
        rd_ptr  <= rd_ptr + GAW'(1);
      end
      // W channel length tracking
      if (w_left == 9'd0 && !lempty) w_left <= lrd;
      else if (wvalid && wready)     w_left <= w_left - 9'd1;

      case ({awvalid && awready, bvalid && bready})
        2'b10:   b_out <= b_out + 8'd1;
        2'b01:   b_out <= b_out - 8'd1;
        default: ;
      endcase
    end
  end
endmodule

`endif
