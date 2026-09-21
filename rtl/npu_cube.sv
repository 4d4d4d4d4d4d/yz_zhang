// =====================================================================
// npu_cube.sv -- 16x16 output-stationary outer-product MAC array.
//
//   C[i][j] += A[k][i] * B[k][j]   for k = 0 .. k_len-1
//
// One beat of A and one beat of B per cycle produce 256 MACs. K is
// unbounded: the accumulator is the only state that grows, and acc_cont /
// acc_hold let a partial sum survive across descriptors so a K > 256
// reduction never has to spill to a buffer.
//
// A and B are independent read requesters into the crossbar. They are
// allowed to desync -- each has its own response FIFO and the array
// consumes one beat from each only when both are present. That is what
// makes the array run at full rate when A and B live in different banks
// and degrade gracefully (not deadlock) when they share one.
//
// A read is only requested when a landing slot is already reserved:
// occupancy + outstanding < RDEPTH. SRAM reads cannot be back-pressured.
// =====================================================================
`ifndef NPU_CUBE_SV
`define NPU_CUBE_SV

module npu_cube
  import npu_pkg::*;
  import npu_fp::*;
(
  input  logic                clk,
  input  logic                rst_n,

  input  logic                iss_valid,
  input  op_t                 iss_op,

  // crossbar read ports: 0 = A, 1 = B
  output logic [1:0]          rd_req,
  output logic [1:0][GAW-1:0] rd_addr,
  input  logic [1:0]          rd_gnt,
  input  logic [1:0]          rd_rvalid,
  input  logic [1:0][BUS_W-1:0] rd_rdata,

  // crossbar write port
  output logic                wr_req,
  output logic [GAW-1:0]      wr_addr,
  output logic [BUS_W-1:0]    wr_data,
  output logic [LANES-1:0]    wr_mask,
  input  logic                wr_gnt,

  output logic                cpl_valid,
  output cpl_t                cpl,
  output logic                busy
);

  localparam int RDEPTH = 4;

  // ------------------------------------------------ input queue
  logic            q_pop, q_empty;
  logic [$bits(op_t)-1:0] q_dat;
  logic [$clog2(CREDIT+1)-1:0] q_cnt;
  logic            q_full_unused;

  npu_fifo #(.W($bits(op_t)), .D(CREDIT)) u_iq (
    .clk(clk), .rst_n(rst_n),
    .push(iss_valid), .wdata(iss_op), .full(q_full_unused),
    .pop(q_pop), .rdata(q_dat), .empty(q_empty), .count(q_cnt));

  op_t   cur;
  cube_t cfg;
  assign cfg = cube_t'(cur.pl);

  // ------------------------------------------------ FSM
  typedef enum logic [2:0] {S_IDLE, S_RUN, S_DRAIN, S_WB, S_CPL} st_e;
  st_e st;

  logic [15:0] ka, kb, kdone;     // A-side, B-side and consumed K index
  logic [4:0]  wrow;
  logic        err_q;

  // ------------------------------------------------ operand FIFOs
  logic [1:0] f_push, f_pop, f_empty, f_full;
  logic [1:0][BUS_W-1:0] f_dat;
  logic [1:0][$clog2(RDEPTH+1)-1:0] f_cnt;
  logic [1:0] outst;              // one read is in flight at most (1 cycle)

  for (genvar s = 0; s < 2; s++) begin : g_opf
    npu_fifo #(.W(BUS_W), .D(RDEPTH)) u_f (
      .clk(clk), .rst_n(rst_n),
      .push(f_push[s]), .wdata(rd_rdata[s]), .full(f_full[s]),
      .pop(f_pop[s]), .rdata(f_dat[s]), .empty(f_empty[s]), .count(f_cnt[s]));
    assign f_push[s] = rd_rvalid[s];
  end

  logic [15:0] klen;
  assign klen = cfg.k_len;

  // reserve the landing slot before requesting
  logic [1:0] can_req;
  always_comb
    for (int s = 0; s < 2; s++)
      can_req[s] = ({1'b0, f_cnt[s]} + {{$clog2(RDEPTH+1){1'b0}}, outst[s]})
                   < ($clog2(RDEPTH+1)+1)'(RDEPTH);

  assign rd_req[0] = (st == S_RUN) && !err_q && (ka < klen) && can_req[0];
  assign rd_req[1] = (st == S_RUN) && !err_q && (kb < klen) && can_req[1];
  assign rd_addr[0] = GAW'(16'(cfg.src_a) + ka * cfg.a_stride);
  assign rd_addr[1] = GAW'(16'(cfg.src_b) + kb * cfg.b_stride);

  // ------------------------------------------------ accumulator
  logic [LANES-1:0][LANES-1:0][31:0] acc;
  logic pair;                         // a matched A/B beat pair is available
  assign pair   = !f_empty[0] && !f_empty[1];
  assign f_pop  = {2{pair}};

  logic [BUS_W-1:0] abeat, bbeat;
  assign abeat = f_dat[0];
  assign bbeat = f_dat[1];

  // ------------------------------------------------ writeback
  logic [BUS_W-1:0] wb_beat;
  always_comb begin
    automatic logic [31:0] v;
    automatic logic [15:0] b;
    wb_beat = '0;
    v = '0;
    b = '0;
    for (int j = 0; j < LANES; j++) begin
      v = acc[wrow[3:0]][j];
      b = cur.hdr.fp ? fp32_to_bf16(v) : shift_sat(signed'(v), cfg.shift);
      if (cfg.relu && b[15]) b = 16'h0000;    // sign bit is the ReLU test
      wb_beat[j*ELEM_W +: ELEM_W] = b;
    end
  end

  assign wr_req  = (st == S_WB);
  assign wr_addr = GAW'(16'(cfg.dst) + 16'(wrow) * cfg.c_stride);
  assign wr_data = wb_beat;
  always_comb begin
    wr_mask = '0;
    for (int j = 0; j < LANES; j++) if (j <= int'(cfg.n_dim)) wr_mask[j] = 1'b1;
  end

  // ------------------------------------------------ config check
  logic  cfg_err, is_nop;
  op_t   nq_op;
  cube_t nq_cfg;
  assign nq_op  = op_t'(q_dat);
  assign nq_cfg = cube_t'(nq_op.pl);

  always_comb begin
    automatic op_t   o = nq_op;
    automatic cube_t c = nq_cfg;
    is_nop  = (o.hdr.opc == OPC_NOP);
    cfg_err = 1'b0;
    if (!is_nop) begin
      if (o.hdr.opc != C_MM)                              cfg_err = 1'b1;
      if (c.k_len == 16'd0)                               cfg_err = 1'b1;
      if (addr_ovf(c.src_a, c.k_len, c.a_stride))         cfg_err = 1'b1;
      if (addr_ovf(c.src_b, c.k_len, c.b_stride))         cfg_err = 1'b1;
      if (!c.acc_hold &&
          addr_ovf(c.dst, 16'(c.rows) + 16'd1, c.c_stride)) cfg_err = 1'b1;
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
      st    <= S_IDLE;
      ka    <= '0; kb <= '0; kdone <= '0; wrow <= '0;
      err_q <= 1'b0;
      cur   <= '0;
      outst <= '0;
      for (int i = 0; i < LANES; i++)
        for (int j = 0; j < LANES; j++) acc[i][j] <= '0;
    end else begin
      outst <= rd_req & rd_gnt;

      unique case (st)
        S_IDLE: if (!q_empty) begin
          cur   <= nq_op;
          err_q <= cfg_err;
          ka    <= '0; kb <= '0; kdone <= '0; wrow <= '0;
          if (cfg_err || is_nop) begin
            st <= S_CPL;
          end else begin
            st <= S_RUN;
            if (!nq_cfg.acc_cont)
              for (int i = 0; i < LANES; i++)
                for (int j = 0; j < LANES; j++) acc[i][j] <= '0;
          end
        end

        S_RUN: begin
          if (rd_req[0] && rd_gnt[0]) ka <= ka + 1'b1;
          if (rd_req[1] && rd_gnt[1]) kb <= kb + 1'b1;
          if (pair) begin
            kdone <= kdone + 1'b1;
            for (int i = 0; i < LANES; i++)
              for (int j = 0; j < LANES; j++)
                if (i <= int'(cfg.rows) && j <= int'(cfg.n_dim)) begin
                  if (cur.hdr.fp)
                    acc[i][j] <= fp32_add(acc[i][j],
                                          bf16_mul(abeat[i*ELEM_W +: ELEM_W],
                                                   bbeat[j*ELEM_W +: ELEM_W]));
                  else
                    acc[i][j] <= acc[i][j] +
                       32'(signed'(abeat[i*ELEM_W +: ELEM_W]) *
                           signed'(bbeat[j*ELEM_W +: ELEM_W]));
                end
            if (kdone + 16'd1 == klen)
              st <= cfg.acc_hold ? S_CPL : S_WB;
          end
        end

        S_WB: if (wr_gnt) begin
          if (wrow == 5'(cfg.rows)) st <= S_CPL;
          else                  wrow <= wrow + 1'b1;
        end

        S_CPL: st <= S_IDLE;

        default: st <= S_IDLE;
      endcase
    end
  end

endmodule

`endif
