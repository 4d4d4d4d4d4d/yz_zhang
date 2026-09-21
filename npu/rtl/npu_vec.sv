// =====================================================================
// npu_vec.sv -- 16-lane SIMD unit.
//
// One beat (16 lanes) per cycle when its operands and a write grant are
// available. Opcode classes and how each one fetches its B operand:
//
//   none    MOV ADDI MULI MAXI RECIP CVT_F2I CVT_I2F RED_SUM RED_MAX SEL
//   stream  ADD SUB MUL MAX MIN SELD                 one B beat per row
//   once    BRC_R                    one B beat, a row vector, held
//   column  BRC_C                    one B beat per 16 rows, lane = row%16
//   lut     LUT                      two B beats: slopes then intercepts
//
// Every VEC write is predicated by cfg.mask, and SELD further predicates
// per lane on the sign of B. Lane-granular writes are exactly why the ECC
// code word is 16 bits wide (see npu_ecc.sv).
//
// Row reductions pack one scalar per row into consecutive lanes and emit a
// beat every 16 rows, which is why a reduced vector is contiguous and why
// the compiler has to insert a transpose when CUBE wants the other layout.
// =====================================================================
`ifndef NPU_VEC_SV
`define NPU_VEC_SV

module npu_vec
  import npu_pkg::*;
  import npu_fp::*;
(
  input  logic                  clk,
  input  logic                  rst_n,

  input  logic                  iss_valid,
  input  op_t                   iss_op,

  output logic [1:0]            rd_req,
  output logic [1:0][GAW-1:0]   rd_addr,
  input  logic [1:0]            rd_gnt,
  input  logic [1:0]            rd_rvalid,
  input  logic [1:0][BUS_W-1:0] rd_rdata,

  output logic                  wr_req,
  output logic [GAW-1:0]        wr_addr,
  output logic [BUS_W-1:0]      wr_data,
  output logic [LANES-1:0]      wr_mask,
  input  logic                  wr_gnt,

  output logic                  cpl_valid,
  output cpl_t                  cpl,
  output logic                  busy
);

  localparam int RDEPTH = 4;

  // B fetch modes
  localparam logic [2:0] BM_NONE = 3'd0;
  localparam logic [2:0] BM_STR  = 3'd1;
  localparam logic [2:0] BM_ONCE = 3'd2;
  localparam logic [2:0] BM_COL  = 3'd3;
  localparam logic [2:0] BM_LUT  = 3'd4;

  function automatic logic [2:0] bmode(input logic [5:0] o);
    unique case (o)
      V_ADD, V_SUB, V_MUL, V_MAX, V_MIN, V_SELD: return BM_STR;
      V_BRC_R:                                   return BM_ONCE;
      V_BRC_C:                                   return BM_COL;
      V_LUT:                                     return BM_LUT;
      default:                                   return BM_NONE;
    endcase
  endfunction

  function automatic logic is_red(input logic [5:0] o);
    return (o == V_RED_SUM) || (o == V_RED_MAX);
  endfunction

  function automatic logic opc_ok(input logic [5:0] o);
    return (o <= V_CVT_I2F) || (o == OPC_NOP);
  endfunction

  // ------------------------------------------------ ALU
  function automatic logic [15:0] bin_op(input logic [1:0]  s,
                                         input logic        fp,
                                         input logic [15:0] a,
                                         input logic [15:0] b,
                                         input logic [4:0]  sh);
    logic signed [31:0] x, y;
    if (fp) begin
      unique case (s)
        SUB_ADD: return fp32_to_bf16(fp32_add(bf16_to_fp32(a), bf16_to_fp32(b)));
        SUB_SUB: return fp32_to_bf16(fp32_add(bf16_to_fp32(a),
                                              bf16_to_fp32({~b[15], b[14:0]})));
        SUB_MUL: return fp32_to_bf16(bf16_mul(a, b));
        default: return bf16_gt(a, b) ? a : b;
      endcase
    end
    x = 32'(signed'(a));
    y = 32'(signed'(b));
    unique case (s)
      SUB_ADD: return sat16(x + y);
      SUB_SUB: return sat16(x - y);
      SUB_MUL: return shift_sat(x * y, sh);
      default: return (x > y) ? a : b;
    endcase
  endfunction

  // ------------------------------------------------ input queue
  logic q_pop, q_empty, q_full_unused;
  logic [$bits(op_t)-1:0] q_dat;
  logic [$clog2(CREDIT+1)-1:0] q_cnt;

  npu_fifo #(.W($bits(op_t)), .D(CREDIT)) u_iq (
    .clk(clk), .rst_n(rst_n),
    .push(iss_valid), .wdata(iss_op), .full(q_full_unused),
    .pop(q_pop), .rdata(q_dat), .empty(q_empty), .count(q_cnt));

  op_t  nq_op;  assign nq_op  = op_t'(q_dat);
  vec_t nq_cfg; assign nq_cfg = vec_t'(nq_op.pl);

  op_t  cur;
  vec_t cfg;   assign cfg = vec_t'(cur.pl);

  logic [5:0]  opc;   assign opc  = cur.hdr.opc;
  logic [2:0]  bm;    assign bm   = bmode(opc);
  logic        red;   assign red  = is_red(opc);
  logic        fp;    assign fp   = cur.hdr.fp;
  logic [15:0] rows;  assign rows = cfg.rows;

  // number of B beats the descriptor needs
  function automatic logic [15:0] bcount_of(input logic [2:0] m,
                                            input logic [15:0] r);
    unique case (m)
      BM_STR:  return r;
      BM_ONCE: return 16'd1;
      BM_COL:  return (r + 16'd15) >> 4;
      BM_LUT:  return 16'd2;
      default: return 16'd0;
    endcase
  endfunction

  // ------------------------------------------------ FSM
  typedef enum logic [2:0] {S_IDLE, S_PRE, S_RUN, S_CPL} st_e;
  st_e st;

  logic [15:0] ka, kb;      // request counters
  logic [15:0] row;         // rows consumed
  logic [15:0] pre_got;     // constants latched in S_PRE
  logic        err_q;
  logic [BUS_W-1:0] kreg [2];

  // ------------------------------------------------ operand FIFOs
  logic [1:0] f_push, f_pop, f_empty, f_full;
  logic [1:0][BUS_W-1:0] f_dat;
  logic [1:0][$clog2(RDEPTH+1)-1:0] f_cnt;
  logic [1:0] outst;

  for (genvar s = 0; s < 2; s++) begin : g_opf
    npu_fifo #(.W(BUS_W), .D(RDEPTH)) u_f (
      .clk(clk), .rst_n(rst_n),
      .push(f_push[s]), .wdata(rd_rdata[s]), .full(f_full[s]),
      .pop(f_pop[s]), .rdata(f_dat[s]), .empty(f_empty[s]), .count(f_cnt[s]));
    assign f_push[s] = rd_rvalid[s];
  end

  logic [1:0] can_req;
  always_comb
    for (int s = 0; s < 2; s++)
      can_req[s] = ({1'b0, f_cnt[s]} + {{$clog2(RDEPTH+1){1'b0}}, outst[s]})
                   < ($clog2(RDEPTH+1)+1)'(RDEPTH);

  logic [15:0] bcnt;
  assign bcnt = bcount_of(bm, rows);

  logic run_or_pre;
  assign run_or_pre = (st == S_RUN) || (st == S_PRE);

  assign rd_req[0]  = (st == S_RUN) && !err_q && (ka < rows) && can_req[0];
  assign rd_req[1]  = run_or_pre && !err_q && (kb < bcnt) && can_req[1];
  assign rd_addr[0] = GAW'(16'(cfg.src_a) + ka * cfg.a_stride);
  assign rd_addr[1] = GAW'(16'(cfg.src_b) + kb * cfg.b_stride);

  // ------------------------------------------------ datapath
  logic [BUS_W-1:0] abeat, bbeat, bheld;
  assign abeat = f_dat[0];
  assign bbeat = f_dat[1];
  assign bheld = kreg[0];

  // B operand per lane, by fetch mode
  logic [BUS_W-1:0] bval;
  always_comb begin
    automatic logic [15:0] col;
    bval = '0;
    col  = '0;
    unique case (bm)
      BM_STR:  bval = bbeat;
      BM_ONCE: bval = bheld;                            // row vector
      BM_COL: begin
                col = bheld[row[3:0]*ELEM_W +: ELEM_W]; // one scalar per row
                for (int l = 0; l < LANES; l++) bval[l*ELEM_W +: ELEM_W] = col;
              end
      default: ;
    endcase
  end

  // LUT segment index, clamped to [0,15]
  function automatic logic [3:0] lut_idx(input logic        f,
                                         input logic [15:0] a,
                                         input logic [20:0] imm);
    logic signed [31:0] t;
    if (f) t = fp32_to_int(fp32_add(bf16_to_fp32(a),
                                    bf16_to_fp32({~imm[15], imm[14:0]})),
                           imm[20:16]);
    else   t = (32'(signed'(a)) - 32'(signed'(imm[15:0]))) >>> imm[20:16];
    if (t < 32'sd0)  return 4'd0;
    if (t > 32'sd15) return 4'd15;
    return t[3:0];
  endfunction

  logic [BUS_W-1:0] res;
  always_comb begin
    automatic logic [15:0] a, b, y;
    automatic logic [3:0]  ix;
    res = '0;
    a = '0; b = '0; y = '0; ix = '0;
    for (int l = 0; l < LANES; l++) begin
      a = abeat[l*ELEM_W +: ELEM_W];
      b = bval [l*ELEM_W +: ELEM_W];
      unique case (opc)
        V_MOV, V_SEL, V_SELD: y = a;
        V_ADDI:  y = bin_op(SUB_ADD, fp, a, cfg.imm[15:0], cfg.imm[20:16]);
        V_MULI:  y = bin_op(SUB_MUL, fp, a, cfg.imm[15:0], cfg.imm[20:16]);
        V_MAXI:  y = bin_op(SUB_MAX, fp, a, cfg.imm[15:0], cfg.imm[20:16]);
        V_ADD:   y = bin_op(SUB_ADD, fp, a, b, cfg.imm[20:16]);
        V_SUB:   y = bin_op(SUB_SUB, fp, a, b, cfg.imm[20:16]);
        V_MUL:   y = bin_op(SUB_MUL, fp, a, b, cfg.imm[20:16]);
        V_MAX:   y = bin_op(SUB_MAX, fp, a, b, cfg.imm[20:16]);
        V_MIN:   y = bin_op(SUB_MAX, fp, a, b, cfg.imm[20:16]) == a ? b : a;
        V_BRC_R,
        V_BRC_C: y = bin_op(cfg.subop, fp, a, b, cfg.imm[20:16]);
        V_RECIP: y = bf16_recip(a);
        V_CVT_F2I: y = sat16(fp32_to_int(bf16_to_fp32(a), cfg.imm[20:16]));
        V_CVT_I2F: y = fp32_to_bf16(int_to_fp32(32'(signed'(a)), cfg.imm[20:16]));
        V_LUT: begin
                 ix = lut_idx(fp, a, cfg.imm[20:0]);
                 y  = bin_op(SUB_ADD, fp,
                             bin_op(SUB_MUL, fp, a,
                                    kreg[0][ix*ELEM_W +: ELEM_W], cfg.imm[25:21]),
                             kreg[1][ix*ELEM_W +: ELEM_W], 5'd0);
               end
        default: y = a;
      endcase
      res[l*ELEM_W +: ELEM_W] = y;
    end
  end

  // ---- row reduction: one scalar per row, packed 16 per beat ----
  logic [15:0] red_scalar;
  always_comb begin
    automatic logic [31:0] acc;
    automatic logic [15:0] m16;
    automatic logic [15:0] v;
    automatic logic        first;
    acc   = '0;
    m16   = '0;
    v     = '0;
    first = 1'b1;
    if (opc == V_RED_SUM) begin
      for (int l = 0; l < LANES; l++)
        if (cfg.mask[l]) begin
          if (fp) acc = fp32_add(acc, bf16_to_fp32(abeat[l*ELEM_W +: ELEM_W]));
          else    acc = acc + 32'(signed'(abeat[l*ELEM_W +: ELEM_W]));
        end
      red_scalar = fp ? fp32_to_bf16(acc) : shift_sat(signed'(acc), cfg.imm[20:16]);
    end else begin
      for (int l = 0; l < LANES; l++)
        if (cfg.mask[l]) begin
          v = abeat[l*ELEM_W +: ELEM_W];
          if (first) begin
            m16   = v;
            first = 1'b0;
          end else begin
            m16 = fp ? (bf16_gt(v, m16) ? v : m16)
                     : ((signed'(v) > signed'(m16)) ? v : m16);
          end
        end
      red_scalar = m16;
    end
  end

  logic [BUS_W-1:0] pack;
  logic [LANES-1:0] pack_mask;

  // ---- write shaping ----
  logic last_row, red_flush;
  assign last_row  = (row + 16'd1 == rows);
  assign red_flush = red && ((row[3:0] == 4'd15) || last_row);

  logic [LANES-1:0] pred;
  always_comb begin
    automatic logic [15:0] bb;
    bb   = '0;
    pred = cfg.mask;
    if (opc == V_SELD)
      for (int l = 0; l < LANES; l++) begin
        bb = bval[l*ELEM_W +: ELEM_W];
        pred[l] = cfg.mask[l] &&
                  (fp ? (!bb[15] && (bb[14:0] != 15'd0)) : (signed'(bb) > 16'sd0));
      end
  end

  logic consume;                        // a row is retired this cycle
  logic want_write;

  assign want_write = red ? red_flush : 1'b1;
  assign wr_req  = (st == S_RUN) && !err_q && !f_empty[0]
                   && (!b_needed || !f_empty[1]) && want_write;
  assign wr_addr = red ? GAW'(16'(cfg.dst) + (row >> 4) * cfg.d_stride)
                       : GAW'(16'(cfg.dst) + row * cfg.d_stride);
  assign wr_data = red ? (pack | (BUS_W'(red_scalar) << (row[3:0] * ELEM_W)))
                       : res;
  always_comb begin
    wr_mask = pred;
    if (red) begin
      wr_mask = pack_mask;
      wr_mask[row[3:0]] = 1'b1;
    end
  end

  logic b_needed;
  always_comb begin
    unique case (bm)
      BM_STR:  b_needed = 1'b1;
      BM_COL:  b_needed = (row[3:0] == 4'd0);
      default: b_needed = 1'b0;
    endcase
  end

  assign consume = (st == S_RUN) && !err_q && !f_empty[0]
                   && (!b_needed || !f_empty[1])
                   && (!want_write || wr_gnt);

  assign f_pop[0] = consume;
  assign f_pop[1] = (st == S_PRE)
                      ? !f_empty[1]
                      : (consume && b_needed && (bm == BM_STR || bm == BM_COL));

  // ------------------------------------------------ config check
  logic cfg_err, is_nop;
  always_comb begin
    automatic op_t   o = nq_op;
    automatic vec_t  c = nq_cfg;
    automatic logic [2:0]  m  = bmode(o.hdr.opc);
    automatic logic [15:0] bn = bcount_of(m, c.rows);
    automatic logic [15:0] nw = is_red(o.hdr.opc) ? ((c.rows + 16'd15) >> 4)
                                                  : c.rows;
    is_nop  = (o.hdr.opc == OPC_NOP);
    cfg_err = 1'b0;
    if (!is_nop) begin
      if (!opc_ok(o.hdr.opc))                        cfg_err = 1'b1;
      if (c.rows == 16'd0)                           cfg_err = 1'b1;
      if (addr_ovf(c.src_a, c.rows, c.a_stride))     cfg_err = 1'b1;
      if (addr_ovf(c.dst,   nw,     c.d_stride))     cfg_err = 1'b1;
      if (m != BM_NONE && addr_ovf(c.src_b, bn, c.b_stride)) cfg_err = 1'b1;
      // RECIP is defined on bf16 only
      if ((o.hdr.opc == V_RECIP) && !o.hdr.fp)       cfg_err = 1'b1;
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

  // ------------------------------------------------ sequencer
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      st  <= S_IDLE;
      ka <= '0; kb <= '0; row <= '0; pre_got <= '0;
      err_q <= 1'b0; cur <= '0; outst <= '0;
      pack <= '0; pack_mask <= '0;
      kreg[0] <= '0; kreg[1] <= '0;
    end else begin
      outst <= rd_req & rd_gnt;

      unique case (st)
        S_IDLE: if (!q_empty) begin
          cur     <= nq_op;
          err_q   <= cfg_err;
          ka      <= '0; kb <= '0; row <= '0; pre_got <= '0;
          pack    <= '0; pack_mask <= '0;
          if (cfg_err || (nq_op.hdr.opc == OPC_NOP)) st <= S_CPL;
          else if (bmode(nq_op.hdr.opc) == BM_ONCE ||
                   bmode(nq_op.hdr.opc) == BM_LUT)  st <= S_PRE;
          else                                      st <= S_RUN;
        end

        // latch the held constants (row vector, or LUT slopes+intercepts)
        S_PRE: begin
          if (rd_req[1] && rd_gnt[1]) kb <= kb + 1'b1;
          if (!f_empty[1]) begin
            kreg[pre_got[0]] <= f_dat[1];
            pre_got          <= pre_got + 1'b1;
            if (pre_got + 16'd1 == bcnt) st <= S_RUN;
          end
        end

        S_RUN: begin
          if (rd_req[0] && rd_gnt[0]) ka <= ka + 1'b1;
          if (rd_req[1] && rd_gnt[1]) kb <= kb + 1'b1;
          if (consume && b_needed && bm == BM_COL) kreg[0] <= f_dat[1];
          if (consume) begin
            if (red) begin
              if (red_flush) begin
                pack      <= '0;
                pack_mask <= '0;
              end else begin
                pack      <= pack | (BUS_W'(red_scalar) << (row[3:0] * ELEM_W));
                pack_mask <= pack_mask | (LANES'(1) << row[3:0]);
              end
            end
            if (last_row) st <= S_CPL;
            else          row <= row + 1'b1;
          end
        end

        S_CPL: st <= S_IDLE;

        default: st <= S_IDLE;
      endcase
    end
  end

endmodule

`endif
