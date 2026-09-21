// CUBE against a behavioural golden model, through the real crossbar.
// The testbench owns write port 3 and read port 5 to preload operands and
// read results back, so the data path under test is the production one.
module tb_cube;
  import npu_pkg::*;
  import npu_fp::*;
`include "tb_fp_util.svh"

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;

  logic [5:0]              rd_req;
  logic [5:0][GAW-1:0]     rd_addr;
  logic [5:0]              rd_gnt, rd_rvalid;
  logic [5:0][BUS_W-1:0]   rd_rdata;
  logic [3:0]              wr_req;
  logic [3:0][GAW-1:0]     wr_addr;
  logic [3:0][BUS_W-1:0]   wr_data;
  logic [3:0][LANES-1:0]   wr_mask;
  logic [3:0]              wr_gnt;
  logic                    ecc_ce, ecc_ue;
  logic [BUFIDW+BUF_AW-1:0] ecc_loc;

  npu_xbar u_xbar (
    .clk(clk), .rst_n(rst_n),
    .rd_req(rd_req), .rd_addr(rd_addr), .rd_gnt(rd_gnt),
    .rd_rvalid(rd_rvalid), .rd_rdata(rd_rdata),
    .wr_req(wr_req), .wr_addr(wr_addr), .wr_data(wr_data),
    .wr_mask(wr_mask), .wr_gnt(wr_gnt),
    .ecc_inj(2'b00), .ecc_inj_buf(2'd0),
    .ecc_ce(ecc_ce), .ecc_ue(ecc_ue), .ecc_loc(ecc_loc));

  logic        iss_valid;
  op_t         iss_op;
  logic        cpl_valid, cube_busy;
  cpl_t        cpl;

  npu_cube u_dut (
    .clk(clk), .rst_n(rst_n),
    .iss_valid(iss_valid), .iss_op(iss_op),
    .rd_req(rd_req[1:0]), .rd_addr(rd_addr[1:0]), .rd_gnt(rd_gnt[1:0]),
    .rd_rvalid(rd_rvalid[1:0]), .rd_rdata(rd_rdata[1:0]),
    .wr_req(wr_req[0]), .wr_addr(wr_addr[0]), .wr_data(wr_data[0]),
    .wr_mask(wr_mask[0]), .wr_gnt(wr_gnt[0]),
    .cpl_valid(cpl_valid), .cpl(cpl), .busy(cube_busy));

  assign rd_req[4:2]  = '0;
  assign rd_addr[4:2] = '0;
  assign wr_req[2:1]  = '0;
  assign wr_addr[2:1] = '0;
  assign wr_data[2:1] = '0;
  assign wr_mask[2:1] = '0;

  // ---------------- backdoor-ish access through real ports ----------------
  task automatic wr_beat(input logic [GAW-1:0] a, input logic [BUS_W-1:0] d);
    @(negedge clk);
    wr_req[3]  = 1'b1; wr_addr[3] = a; wr_data[3] = d; wr_mask[3] = '1;
    @(posedge clk);
    while (!wr_gnt[3]) @(posedge clk);
    @(negedge clk);
    wr_req[3] = 1'b0;
  endtask

  task automatic rd_beat(input logic [GAW-1:0] a, output logic [BUS_W-1:0] d);
    @(negedge clk);
    rd_req[5] = 1'b1; rd_addr[5] = a;
    @(posedge clk);
    while (!rd_gnt[5]) @(posedge clk);
    @(negedge clk);
    rd_req[5] = 1'b0;
    @(posedge clk);
    while (!rd_rvalid[5]) @(posedge clk);
    d = rd_rdata[5];
  endtask

  // ---------------- golden ----------------
  int errors = 0;
  logic [15:0] A [256][16];
  logic [15:0] B [256][16];

  task automatic run_case(input int K, input int ROWS, input int NDIM,
                          input bit fp, input int shift, input bit relu);
    logic [BUS_W-1:0] beat, got;
    cube_t c;
    op_t   o;
    real   gacc;
    int    iacc;
    real   want, gotv;

    // ---- operands ----
    for (int k = 0; k < K; k++) begin
      for (int i = 0; i < 16; i++) begin
        A[k][i] = fp ? d2bf(($urandom_range(0, 4000) / 1000.0) - 2.0)
                     : 16'($urandom_range(0, 200) - 100);
        B[k][i] = fp ? d2bf(($urandom_range(0, 4000) / 1000.0) - 2.0)
                     : 16'($urandom_range(0, 200) - 100);
      end
      beat = '0;
      for (int i = 0; i < 16; i++) beat[i*16 +: 16] = A[k][i];
      wr_beat(GAW'(10'h000 + k), beat);          // buffer 0
      beat = '0;
      for (int i = 0; i < 16; i++) beat[i*16 +: 16] = B[k][i];
      wr_beat(GAW'(10'h100 + k), beat);          // buffer 1
    end

    // ---- descriptor ----
    c          = '0;
    c.src_a    = 16'h0000;
    c.src_b    = 16'h0100;
    c.dst      = 16'h0200;                        // buffer 2
    c.k_len    = 16'(K);
    c.a_stride = 16'd1;
    c.b_stride = 16'd1;
    c.c_stride = 16'd1;
    c.rows     = 4'(ROWS - 1);
    c.n_dim    = 4'(NDIM - 1);
    c.shift    = 5'(shift);
    c.relu     = relu;

    o            = '0;
    o.hdr.vld    = 1'b1;
    o.hdr.pipe   = 3'(P_CUBE);
    o.hdr.opc    = C_MM;
    o.hdr.tag    = 8'hA5;
    o.hdr.fp     = fp;
    o.pl         = c;
    o.qid        = 3'd2;
    o.mcu        = 2'd1;

    @(negedge clk); iss_valid = 1'b1; iss_op = o;
    @(negedge clk); iss_valid = 1'b0;
    while (!cpl_valid) @(posedge clk);
    if (cpl.err) begin
      errors++; $display("FAIL: unexpected err for K=%0d", K);
    end
    if (cpl.tag !== 8'hA5 || cpl.qid !== 3'd2 || cpl.mcu !== 2'd1) begin
      errors++; $display("FAIL: completion identity wrong");
    end
    @(posedge clk);

    // ---- check ----
    for (int i = 0; i < ROWS; i++) begin
      rd_beat(GAW'(10'h200 + i), got);
      for (int j = 0; j < NDIM; j++) begin
        if (fp) begin
          logic [31:0] acc32;
          acc32 = 32'd0;
          for (int k = 0; k < K; k++)
            acc32 = fp32_add(acc32, bf16_mul(A[k][i], B[k][j]));
          want = f2d({fp32_to_bf16(acc32), 16'h0});
          if (relu && want < 0.0) want = 0.0;
          gotv = bf2d(got[j*16 +: 16]);
          if (relerr(gotv, want) > 1.0e-6) begin
            errors++;
            if (errors < 10)
              $display("FAIL fp K=%0d [%0d][%0d]: got %g want %g", K, i, j, gotv, want);
          end
        end else begin
          logic signed [31:0] s;
          logic [15:0] w;
          s = 0;
          for (int k = 0; k < K; k++)
            s = s + 32'(signed'(A[k][i])) * 32'(signed'(B[k][j]));
          w = shift_sat(s, 5'(shift));
          if (relu && w[15]) w = 16'h0000;
          if (got[j*16 +: 16] !== w) begin
            errors++;
            if (errors < 10)
              $display("FAIL int K=%0d [%0d][%0d]: got %0d want %0d", K, i, j,
                       $signed(got[j*16 +: 16]), $signed(w));
          end
        end
      end
    end
  endtask

  // ---------------- accumulator carry-over across descriptors ----------------
  task automatic run_split(input int K1, input int K2);
    logic [BUS_W-1:0] beat, got;
    cube_t c; op_t o;
    int K = K1 + K2;
    logic signed [31:0] s;

    for (int k = 0; k < K; k++) begin
      for (int i = 0; i < 16; i++) begin
        A[k][i] = 16'($urandom_range(0, 60) - 30);
        B[k][i] = 16'($urandom_range(0, 60) - 30);
      end
      beat = '0;
      for (int i = 0; i < 16; i++) beat[i*16 +: 16] = A[k][i];
      wr_beat(GAW'(10'h000 + k), beat);
      beat = '0;
      for (int i = 0; i < 16; i++) beat[i*16 +: 16] = B[k][i];
      wr_beat(GAW'(10'h100 + k), beat);
    end

    for (int part = 0; part < 2; part++) begin
      c          = '0;
      c.src_a    = 16'(part == 0 ? 0 : K1);
      c.src_b    = 16'h0100 + 16'(part == 0 ? 0 : K1);
      c.dst      = 16'h0300;
      c.k_len    = 16'(part == 0 ? K1 : K2);
      c.a_stride = 16'd1; c.b_stride = 16'd1; c.c_stride = 16'd1;
      c.rows     = 4'd15; c.n_dim = 4'd15; c.shift = 5'd0;
      c.acc_cont = (part == 1);       // keep what the first descriptor left
      c.acc_hold = (part == 0);       // and do not write back yet
      o          = '0;
      o.hdr.vld  = 1'b1; o.hdr.pipe = 3'(P_CUBE); o.hdr.opc = C_MM;
      o.hdr.tag  = 8'(part); o.pl = c;
      @(negedge clk); iss_valid = 1'b1; iss_op = o;
      @(negedge clk); iss_valid = 1'b0;
      while (!cpl_valid) @(posedge clk);
      @(posedge clk);
    end

    for (int i = 0; i < 16; i++) begin
      rd_beat(GAW'(10'h300 + i), got);
      for (int j = 0; j < 16; j++) begin
        s = 0;
        for (int k = 0; k < K; k++)
          s = s + 32'(signed'(A[k][i])) * 32'(signed'(B[k][j]));
        if (got[j*16 +: 16] !== shift_sat(s, 5'd0)) begin
          errors++;
          if (errors < 10)
            $display("FAIL split [%0d][%0d]: got %0d want %0d", i, j,
                     $signed(got[j*16 +: 16]), $signed(shift_sat(s, 5'd0)));
        end
      end
    end
  endtask

  initial begin
    rd_req = '0; rd_addr = '0; wr_req = '0; wr_addr = '0;
    wr_data = '0; wr_mask = '0; iss_valid = 0; iss_op = '0;
    repeat (4) @(posedge clk);
    rst_n = 1;
    repeat (2) @(posedge clk);

    run_case(1,   16, 16, 0, 0,  0);
    run_case(8,   16, 16, 0, 4,  0);
    run_case(64,  16, 16, 0, 8,  0);
    run_case(64,   5,  3, 0, 8,  0);     // tail tile, rows/cols < 16
    run_case(32,  16, 16, 0, 6,  1);     // ReLU
    run_case(16,  16, 16, 1, 0,  0);     // bf16
    run_case(128, 16, 16, 1, 0,  0);
    run_case(128,  7, 11, 1, 0,  1);
    run_split(100, 156);                  // K = 256 across two descriptors

    // ---- a descriptor whose operand window leaves its buffer must error ----
    begin
      cube_t c; op_t o;
      c = '0;
      c.src_a = 16'h00F0; c.src_b = 16'h0100; c.dst = 16'h0200;
      c.k_len = 16'd64;                     // 0xF0 + 63 > 0xFF -> overflow
      c.a_stride = 16'd1; c.b_stride = 16'd1; c.c_stride = 16'd1;
      c.rows = 4'd15; c.n_dim = 4'd15;
      o = '0; o.hdr.vld = 1'b1; o.hdr.pipe = 3'(P_CUBE); o.hdr.opc = C_MM;
      o.hdr.tag = 8'hEE; o.pl = c;
      @(negedge clk); iss_valid = 1'b1; iss_op = o;
      @(negedge clk); iss_valid = 1'b0;
      while (!cpl_valid) @(posedge clk);
      if (!cpl.err) begin
        errors++; $display("FAIL: addr overflow was not reported");
      end
      @(posedge clk);
    end

    // ---- a NOP is legal and must not set err ----
    begin
      op_t o;
      o = '0; o.hdr.vld = 1'b1; o.hdr.pipe = 3'(P_CUBE); o.hdr.opc = OPC_NOP;
      o.hdr.tag = 8'h77; o.hdr.set_en = 1'b1; o.hdr.set_evt = 4'd3;
      @(negedge clk); iss_valid = 1'b1; iss_op = o;
      @(negedge clk); iss_valid = 1'b0;
      while (!cpl_valid) @(posedge clk);
      if (cpl.err || !cpl.set_en || cpl.set_evt !== 4'd3) begin
        errors++; $display("FAIL: zero-length op mishandled");
      end
      @(posedge clk);
    end

    if (errors == 0) $display("TEST PASSED (tb_cube)");
    else             $display("TEST FAILED (tb_cube): %0d errors", errors);
    $finish;
  end

  initial begin
    #4000000;
    $display("TEST FAILED (tb_cube): timeout");
    $finish;
  end
endmodule
