// =====================================================================
// npu_pkg.sv -- global parameters, descriptor layout, opcode encoding
// =====================================================================
`ifndef NPU_PKG_SV
`define NPU_PKG_SV

package npu_pkg;

  // ---------------- datapath geometry ----------------
  parameter int LANES    = 16;               // SIMD lanes / systolic tile edge
  parameter int ELEM_W   = 16;               // int16 or bf16
  parameter int BUS_W    = LANES * ELEM_W;   // 256 bit on-chip bus
  parameter int ACC_W    = 32;               // int32 / fp32 accumulator
  parameter int BEAT_B   = BUS_W / 8;        // 32 bytes per beat

  // ---------------- on-chip buffers ----------------
  parameter int NBUF     = 4;
  parameter int BUF_D    = 256;              // beats per buffer
  parameter int BUF_AW   = 8;                // $clog2(BUF_D)
  parameter int BUFIDW   = 2;                // $clog2(NBUF)
  parameter int GAW      = BUF_AW + BUFIDW;  // 10 -- {buf, beat}

  // ---------------- control plane ----------------
  parameter int NMCU     = 4;
  parameter int NQ       = 8;
  parameter int QD       = 16;
  parameter int QIDW     = 3;
  parameter int MCUW     = 2;
  parameter int NPIPE    = 5;
  parameter int PIPEW    = 3;
  parameter int NEVT     = 16;
  parameter int EVT_W    = 3;                // saturating event counter
  parameter int WIN      = 8;                // issue window depth
  parameter int CREDIT   = 4;                // per-pipe issue credits
  parameter int CRDW     = 3;                // $clog2(CREDIT)+1
  parameter int TAG_W    = 8;
  parameter int DESC_W   = 256;
  parameter int NLOCK    = 8;                // hardware semaphores

  // ---------------- ECC : SECDED(22,16) per lane ----------------
  parameter int ECC_K    = ELEM_W;           // 16 data
  parameter int ECC_H    = 5;                // hamming parity
  parameter int ECC_P    = ECC_H + 1;        // + overall parity = 6
  parameter int ECC_N    = ECC_K + ECC_P;    // 22
  parameter int LINE_W   = LANES * ECC_N;    // 352 stored bits per beat

  // ---------------- external memory (AXI4) ----------------
  parameter int AXI_AW   = 32;
  parameter int AXI_DW   = BUS_W;            // 256 bit data bus
  parameter int AXI_IDW  = 2;                // 4 outstanding IDs
  parameter int NID      = 1 << AXI_IDW;
  parameter int MAX_BURST= 16;               // beats per AXI burst

  // ---------------- AXI4-Lite control ----------------
  parameter int LT_AW    = 12;
  parameter int LT_DW    = 32;

  // =================== enumerations ===================
  typedef enum logic [PIPEW-1:0] {
    P_CUBE    = 3'd0,
    P_VEC     = 3'd1,
    P_FIX     = 3'd2,
    P_MTE_IN  = 3'd3,
    P_MTE_OUT = 3'd4
  } pipe_e;

  // Universal no-op, accepted by every pipe. A descriptor may set exactly
  // one event, so waking N consumers costs N-1 trailing NOPs on the same
  // pipe. This is a real ISA limit; see docs/spec_isa.md for the bitmap
  // alternative that was considered and deferred.
  parameter logic [5:0] OPC_NOP  = 6'h3F;

  // CUBE opcodes
  parameter logic [5:0] C_MM     = 6'd0;   // C = A^T * B  (outer-product accumulate)

  // VEC opcodes
  parameter logic [5:0] V_MOV    = 6'd0;   // dst = a
  parameter logic [5:0] V_ADDI   = 6'd1;   // dst = a + imm
  parameter logic [5:0] V_MULI   = 6'd2;   // dst = a * imm
  parameter logic [5:0] V_MAXI   = 6'd3;   // dst = max(a, imm)      (ReLU with imm=0)
  parameter logic [5:0] V_ADD    = 6'd4;   // dst = a + b
  parameter logic [5:0] V_SUB    = 6'd5;
  parameter logic [5:0] V_MUL    = 6'd6;
  parameter logic [5:0] V_MAX    = 6'd7;
  parameter logic [5:0] V_MIN    = 6'd8;
  parameter logic [5:0] V_BRC_R  = 6'd9;   // dst[r][l] = a[r][l] op bvec[l]   (row vector)
  parameter logic [5:0] V_BRC_C  = 6'd10;  // dst[r][l] = a[r][l] op bcol[r]   (column scalar)
  parameter logic [5:0] V_RED_SUM= 6'd11;  // one scalar per row, packed 16/beat
  parameter logic [5:0] V_RED_MAX= 6'd12;
  parameter logic [5:0] V_LUT    = 6'd13;  // 16-segment piecewise linear
  parameter logic [5:0] V_RECIP  = 6'd14;  // reciprocal
  parameter logic [5:0] V_SEL    = 6'd15;  // static lane predicate write
  parameter logic [5:0] V_SELD   = 6'd16;  // data-dependent predicate (b > 0)
  parameter logic [5:0] V_CVT_F2I= 6'd17;  // bf16 -> int16 (imm = shift)
  parameter logic [5:0] V_CVT_I2F= 6'd18;  // int16 -> bf16 (imm = shift)

  // V_BRC_* / V_SELD sub-operation, carried in vec_t.subop
  parameter logic [1:0] SUB_ADD  = 2'd0;
  parameter logic [1:0] SUB_SUB  = 2'd1;
  parameter logic [1:0] SUB_MUL  = 2'd2;
  parameter logic [1:0] SUB_MAX  = 2'd3;

  // FIX opcodes
  parameter logic [5:0] F_TRANS  = 6'd0;   // 16x16 tile transpose

  // MTE opcodes
  parameter logic [5:0] M_XFER   = 6'd0;   // 2-D strided DMA

  // =================== descriptor ===================
  // word 0 : header
  typedef struct packed {
    logic [5:0]  rsvd;
    logic        fp;          // 0 = int16 fixed, 1 = bf16 float
    logic        bar_g;       // global barrier
    logic        bar_q;       // queue-scope barrier
    logic [3:0]  set_evt;
    logic        set_en;
    logic [7:0]  tag;
    logic [5:0]  opc;
    logic [2:0]  pipe;
    logic        vld;         // must be 1; 0 => err_illegal
  } hdr_t;                    // 32 bit

  // word 1 : { 16'b0, wait_mask }
  // words 2..7 : pipe specific payload (192 bit)

  typedef struct packed {          // CUBE payload, 192 bit
    logic [47:0] rsvd;
    logic [15:0] c_stride;    // dst row stride, beats
    logic [15:0] b_stride;    // src_b beat stride along K
    logic [15:0] a_stride;    // src_a beat stride along K
    logic [15:0] k_len;       // reduction length, >= 1
    logic [4:0]  shift;       // acc >> shift on writeback
    logic        relu;
    logic        acc_hold;    // do not write back, keep accumulator
    logic        acc_cont;    // do not clear accumulator on entry
    logic [3:0]  n_dim;       // cols-1 (0..15)
    logic [3:0]  rows;        // rows-1 (0..15)
    logic [15:0] rsvd2;
    logic [15:0] dst;
    logic [15:0] src_b;
    logic [15:0] src_a;
  } cube_t;

  typedef struct packed {          // VEC payload, 192 bit
    logic [29:0] rsvd;
    logic [1:0]  subop;
    logic [31:0] imm;
    logic [15:0] d_stride;
    logic [15:0] b_stride;
    logic [15:0] a_stride;
    logic [15:0] mask;        // static lane predicate
    logic [15:0] rows;        // beats processed, >= 1
    logic [15:0] dst;
    logic [15:0] src_b;
    logic [15:0] src_a;
  } vec_t;

  typedef struct packed {          // FIX payload, 192 bit
    logic [111:0] rsvd;
    logic [15:0]  d_stride;   // beats between output tiles
    logic [15:0]  tiles;      // number of 16x16 tiles, >= 1
    logic [15:0]  dst;
    logic [15:0]  s_stride;   // beats between input tiles
    logic [15:0]  src_a;
  } fix_t;

  typedef struct packed {          // MTE payload, 192 bit
    logic [15:0] rsvd;
    logic [15:0] in_stride;   // intra-row stride in beats (0 => contiguous)
    logic [15:0] in_cnt;      // beats per intra-row group (0 => whole row)
    logic [31:0] ext_rstride; // external row stride, beats
    logic [15:0] rows;        // >= 1
    logic [15:0] cols;        // beats per row, >= 1
    logic [15:0] buf_rstride; // on-chip row stride, beats
    logic [15:0] buf_addr;    // {6'b0, buf[1:0], beat[7:0]}
    logic [47:0] ext_addr;    // byte address, beat aligned
  } mte_t;

  // =================== internal op record ===================
  typedef struct packed {
    hdr_t              hdr;
    logic [NEVT-1:0]   wait_mask;
    logic [191:0]      pl;
    logic [QIDW-1:0]   qid;
    logic [MCUW-1:0]   mcu;
  } op_t;

  // =================== completion ===================
  typedef struct packed {
    logic [TAG_W-1:0]  tag;
    logic [MCUW-1:0]   mcu;
    logic [QIDW-1:0]   qid;
    logic [3:0]        set_evt;
    logic              set_en;
    logic              err;      // configuration error (addr overflow, bad shape)
  } cpl_t;

  // =================== helpers ===================
  function automatic logic [BUFIDW-1:0] a_buf(input logic [15:0] a);
    return a[BUF_AW +: BUFIDW];
  endfunction

  function automatic logic [BUF_AW-1:0] a_beat(input logic [15:0] a);
    return a[BUF_AW-1:0];
  endfunction

  // an operand window must not leave its buffer: base + (n-1)*stride < BUF_D
  function automatic logic addr_ovf(input logic [15:0] base,
                                    input logic [15:0] n,
                                    input logic [15:0] stride);
    logic [31:0] last;
    last = {24'd0, base[BUF_AW-1:0]} + (({16'd0, n} - 32'd1) * {16'd0, stride});
    return (n == 16'd0) || (last >= BUF_D);
  endfunction

endpackage

`endif
