// =====================================================================
// npu_ecc.sv -- SECDED(22,16) per lane.
//
// Why per lane and not per 64 bit: VEC supports lane-granular predicated
// writes, so a beat write may touch an arbitrary subset of the 16 lanes.
// ECC granularity must equal write granularity, otherwise a partial write
// needs read-modify-write on the check bits. 16+6 costs 37.5%; widening to
// 64 bit would cost 12.5% but reintroduces RMW on every predicated store.
//
// Code layout: Hamming(21,16) in classic bit-position form (parity at
// positions 1,2,4,8,16) plus one overall parity bit -> 22.
// =====================================================================
`ifndef NPU_ECC_SV
`define NPU_ECC_SV

package npu_ecc_pkg;

  // data bit i lives at codeword position DPOS[i]  (1-based)
  function automatic int dpos(input int i);
    int k, pos;
    k = 0;
    for (pos = 1; pos <= 21; pos++) begin
      // positions that are a power of two hold parity
      if ((pos & (pos - 1)) != 0) begin
        if (k == i) return pos;
        k++;
      end
    end
    return 0;
  endfunction

  // build the 21-bit Hamming codeword (index 0 == position 1)
  function automatic logic [20:0] hamming_enc(input logic [15:0] d);
    logic [20:0] cw;
    logic        p;
    cw = '0;
    for (int i = 0; i < 16; i++) cw[dpos(i) - 1] = d[i];
    for (int j = 0; j < 5; j++) begin
      p = 1'b0;
      for (int pos = 1; pos <= 21; pos++)
        if ((pos != (1 << j)) && ((pos & (1 << j)) != 0)) p ^= cw[pos - 1];
      cw[(1 << j) - 1] = p;
    end
    return cw;
  endfunction

  function automatic logic [21:0] ecc_enc(input logic [15:0] d);
    logic [20:0] cw;
    cw = hamming_enc(d);
    return {^cw, cw};            // bit 21 = overall parity
  endfunction

  // returns { ue, ce, data[15:0] }
  function automatic logic [17:0] ecc_dec(input logic [21:0] c);
    logic [4:0]  syn;
    logic        pall;
    logic [20:0] cw;
    logic [15:0] d;
    logic        ce, ue;

    cw   = c[20:0];
    pall = ^c;                    // 0 when the 22-bit word has even parity

    for (int j = 0; j < 5; j++) begin
      syn[j] = 1'b0;
      for (int pos = 1; pos <= 21; pos++)
        if ((pos & (1 << j)) != 0) syn[j] ^= cw[pos - 1];
    end

    ce = 1'b0;
    ue = 1'b0;
    if (pall) begin
      // odd parity -> an odd number of flips; syndrome locates it
      ce = 1'b1;
      if (syn != 5'd0 && syn <= 5'd21) cw[syn - 5'd1] = ~cw[syn - 5'd1];
      // syn == 0 means the overall-parity bit itself flipped: data is fine
    end else if (syn != 5'd0) begin
      ue = 1'b1;                  // even parity but non-zero syndrome -> 2 bits
    end

    for (int i = 0; i < 16; i++) d[i] = cw[dpos(i) - 1];
    return {ue, ce, d};
  endfunction

endpackage

// ---------------------------------------------------------------------
// beat-wide encode: 16 lanes x 16 bit -> 16 lanes x 22 bit
// ---------------------------------------------------------------------
module npu_ecc_enc
  import npu_pkg::*;
(
  input  logic [BUS_W-1:0]  data,
  output logic [LINE_W-1:0] line
);
  always_comb
    for (int l = 0; l < LANES; l++)
      line[l*ECC_N +: ECC_N] = npu_ecc_pkg::ecc_enc(data[l*ELEM_W +: ELEM_W]);
endmodule

// ---------------------------------------------------------------------
// beat-wide decode with per-lane CE/UE reporting
// ---------------------------------------------------------------------
module npu_ecc_dec
  import npu_pkg::*;
(
  input  logic [LINE_W-1:0] line,
  output logic [BUS_W-1:0]  data,
  output logic [LANES-1:0]  ce,
  output logic [LANES-1:0]  ue
);
  logic [17:0] r;
  always_comb begin
    for (int l = 0; l < LANES; l++) begin
      r = npu_ecc_pkg::ecc_dec(line[l*ECC_N +: ECC_N]);
      data[l*ELEM_W +: ELEM_W] = r[15:0];
      ce[l]                    = r[16];
      ue[l]                    = r[17];
    end
  end
endmodule

`endif
