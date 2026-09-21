// =====================================================================
// npu_fp.sv -- bf16 / fp32 arithmetic primitives.
//
// Declared semantics (see docs/spec_arith.md):
//   * subnormal inputs and outputs are flushed to zero (FTZ/DAZ)
//   * the only rounding mode is round-to-nearest, ties-to-even
//   * NaN does not propagate a payload: any NaN result is the canonical
//     quiet NaN 0x7FC00000 / 0x7FC0
//   * bf16 x bf16 -> fp32 is EXACT. An 8x8 bit significand product is
//     16 bits and fp32 carries 24, so the multiplier itself never rounds.
//     Rounding happens only when an accumulator is written back.
// =====================================================================
`ifndef NPU_FP_SV
`define NPU_FP_SV

package npu_fp;

  parameter logic [31:0] QNAN32 = 32'h7FC0_0000;

  function automatic logic [31:0] bf16_to_fp32(input logic [15:0] a);
    logic [31:0] r;
    r = {a, 16'h0000};
    if (a[14:7] == 8'h00) r = {a[15], 31'd0};    // flush subnormal to +-0
    return r;
  endfunction

  function automatic logic [15:0] fp32_to_bf16(input logic [31:0] a);
    logic [7:0]  e;
    logic [22:0] m;
    logic [16:0] top;      // {1'b0, a[31:16]} so the round can carry out
    logic        rnd;
    e = a[30:23];
    m = a[22:0];
    if (e == 8'hFF) return (m == 23'd0) ? {a[31], 8'hFF, 7'd0} : 16'h7FC0;
    if (e == 8'h00) return {a[31], 15'd0};       // subnormal -> +-0
    // round to nearest even on bit 15, ties decided by bit 16
    rnd = a[15] && (|a[14:0] || a[16]);
    top = {1'b0, a[31:16]} + {16'd0, rnd};
    if (top[16]) return 16'({a[31], 8'hFF, 7'd0});   // rounded up to infinity
    return top[15:0];
  endfunction

  // exact bf16 x bf16 -> fp32
  function automatic logic [31:0] bf16_mul(input logic [15:0] a,
                                           input logic [15:0] b);
    logic        sa, sb, s;
    logic [7:0]  ea, eb;
    logic [7:0]  ma, mb;
    logic [15:0] p;
    logic signed [10:0] e;
    logic [22:0] frac;

    sa = a[15]; ea = a[14:7]; ma = {1'b1, a[6:0]};
    sb = b[15]; eb = b[14:7]; mb = {1'b1, b[6:0]};
    s  = sa ^ sb;

    if (ea == 8'hFF || eb == 8'hFF) begin
      // inf*0 and any NaN operand -> canonical quiet NaN
      if ((ea == 8'hFF && a[6:0] != 7'd0) || (eb == 8'hFF && b[6:0] != 7'd0))
        return QNAN32;
      if ((ea == 8'hFF && eb == 8'h00) || (eb == 8'hFF && ea == 8'h00))
        return QNAN32;
      return {s, 8'hFF, 23'd0};
    end
    if (ea == 8'h00 || eb == 8'h00) return {s, 31'd0};

    p = ma * mb;                                  // [1,4) in Q14
    e = 11'(signed'({3'd0, ea})) + 11'(signed'({3'd0, eb})) - 11'sd127;
    if (p[15]) begin                              // product >= 2 -> renormalise
      e    = e + 11'sd1;
      frac = {p[14:0], 8'd0};
    end else begin
      frac = {p[13:0], 9'd0};
    end
    if (e >= 11'sd255) return {s, 8'hFF, 23'd0};  // overflow -> infinity
    if (e <= 11'sd0)   return {s, 31'd0};         // underflow -> flush to zero
    return {s, e[7:0], frac};
  endfunction

  // fp32 + fp32, round to nearest even
  function automatic logic [31:0] fp32_add(input logic [31:0] a,
                                           input logic [31:0] b);
    logic        sa, sb;
    logic [7:0]  ea, eb;
    logic [26:0] va, vb, vs, vl;   // {1 hidden, 23 frac, guard, round, sticky}
    logic        ss, sl;
    logic [7:0]  el;
    logic [7:0]  diff;
    logic [27:0] sum;
    logic signed [10:0] eo;
    logic [26:0] mo;
    logic        sticky;
    logic        rup;
    logic        lz_found;
    int          sh;

    sa = a[31]; ea = a[30:23];
    sb = b[31]; eb = b[30:23];

    if (ea == 8'hFF) begin
      if (a[22:0] != 23'd0) return QNAN32;
      if (eb == 8'hFF) begin
        if (b[22:0] != 23'd0) return QNAN32;
        return (sa == sb) ? a : QNAN32;           // inf - inf
      end
      return a;
    end
    if (eb == 8'hFF) return (b[22:0] != 23'd0) ? QNAN32 : b;

    va = (ea == 8'h00) ? 27'd0 : {1'b1, a[22:0], 3'd0};
    vb = (eb == 8'h00) ? 27'd0 : {1'b1, b[22:0], 3'd0};
    if (va == 27'd0 && vb == 27'd0) return {sa & sb, 31'd0};
    if (va == 27'd0) return b;
    if (vb == 27'd0) return a;

    // order operands: l = larger magnitude
    if ({ea, a[22:0]} >= {eb, b[22:0]}) begin
      vl = va; sl = sa; el = ea; vs = vb; ss = sb; diff = ea - eb;
    end else begin
      vl = vb; sl = sb; el = eb; vs = va; ss = sa; diff = eb - ea;
    end

    if (diff > 8'd26) begin
      sticky = (vs != 27'd0);
      vs     = 27'd0;
    end else begin
      sticky = ((vs << (8'd27 - diff)) != 27'd0);
      vs     = vs >> diff;
    end
    vs[0] = vs[0] | sticky;

    if (sl == ss) begin
      sum = {1'b0, vl} + {1'b0, vs};
    end else begin
      sum = {1'b0, vl} - {1'b0, vs};
    end
    if (sum == 28'd0) return 32'd0;

    eo = 11'(signed'({3'd0, el}));
    if (sum[27]) begin                            // carry out of the hidden bit
      mo = sum[27:1];
      mo[0] = mo[0] | sum[0];
      eo = eo + 11'sd1;
    end else begin
      sh       = 0;
      lz_found = 1'b0;
      for (int k = 0; k < 27; k++)
        if (!lz_found && sum[26 - k]) begin
          lz_found = 1'b1;
          sh       = k;
        end
      mo = sum[26:0] << sh;
      eo = eo - 11'(signed'(sh));
    end

    if (eo <= 11'sd0) return {sl, 31'd0};         // underflow -> flush to zero

    // round to nearest even on the 3 low guard bits
    rup = mo[2] && (mo[1] || mo[0] || mo[3]);
    if (rup) begin
      logic [27:0] mr;
      mr = {1'b0, mo} + 28'd8;
      if (mr[27]) begin
        mo = mr[27:1];
        eo = eo + 11'sd1;
      end else begin
        mo = mr[26:0];
      end
    end
    if (eo >= 11'sd255) return {sl, 8'hFF, 23'd0};
    return {sl, eo[7:0], mo[25:3]};
  endfunction

  function automatic logic bf16_gt(input logic [15:0] a, input logic [15:0] b);
    logic [15:0] ka, kb;
    // map to a monotone unsigned key so a plain compare works
    ka = a[15] ? ~a : {1'b1, a[14:0]};
    kb = b[15] ? ~b : {1'b1, b[14:0]};
    return ka > kb;
  endfunction

  // Reciprocal. Exponent is negated exactly; the mantissa uses a Q16
  // Newton-Raphson iteration seeded by the classic minimax line
  //   r0 = 48/17 - 32/17*m'   with m' = m/2 in [0.5,1)
  // Three steps take the initial 6% error below 1 ulp of Q16, which is far
  // tighter than the 8-bit bf16 significand needs. fp only: a fixed-point
  // descriptor with V_RECIP is a configuration error (see spec_isa.md).
  function automatic logic [15:0] bf16_recip(input logic [15:0] a);
    logic [7:0]         e;
    logic signed [63:0] m, r, t;
    logic signed [10:0] eo;
    logic [22:0]        frac;

    e = a[14:7];
    if (e == 8'h00) return {a[15], 8'hFF, 7'd0};                  // 1/0  = inf
    if (e == 8'hFF) return (a[6:0] != 7'd0) ? 16'h7FC0 : {a[15], 15'd0};

    m = 64'(signed'({1'b0, 1'b1, a[6:0], 8'd0}));                 // Q16 in [0.5,1)
    r = 64'sd185044 - ((64'sd123363 * m) >>> 16);                 // seed, Q16

    for (int it = 0; it < 3; it++) begin
      t = (64'sd1 <<< 33) - (m * r);                              // 2 - m*r, Q32
      r = (r * t) >>> 32;                                         // Q16
    end
    // r = 1/m' = 2/m, in (1,2]
    eo = 11'sd253 - 11'(signed'({3'd0, e}));
    if (r >= (64'sd1 <<< 17)) begin                               // r == 2.0
      r  = r >>> 1;
      eo = eo + 11'sd1;
    end
    if (eo <= 11'sd0)   return {a[15], 15'd0};                    // FTZ
    if (eo >= 11'sd255) return {a[15], 8'hFF, 7'd0};
    frac = {r[15:0], 7'd0};
    return fp32_to_bf16({a[15], eo[7:0], frac});
  endfunction

  // ---------------- fp <-> fixed conversion ----------------
  // fp32_to_int returns round-toward-zero of a * 2^sh, saturated to int32.
  function automatic logic signed [31:0] fp32_to_int(input logic [31:0] a,
                                                     input logic [4:0]  sh);
    logic [7:0]         e;
    logic [23:0]        m;
    logic signed [10:0] shamt;
    logic [63:0]        w;
    e = a[30:23];
    if (e == 8'h00) return 32'sd0;                       // includes FTZ input
    if (e == 8'hFF) return a[31] ? -32'sd2147483648 : 32'sd2147483647;
    m     = {1'b1, a[22:0]};
    shamt = 11'(signed'({3'd0, e})) - 11'sd150 + 11'(signed'({6'd0, sh}));
    if (shamt >= 11'sd40)       w = 64'hFFFF_FFFF_FFFF_FFFF;
    else if (shamt >= 11'sd0)   w = {40'd0, m} << shamt[5:0];
    else if (shamt > -11'sd25)  w = {40'd0, m} >> (-shamt[5:0]);
    else                        w = 64'd0;
    if (w > 64'sd2147483647)
      return a[31] ? -32'sd2147483648 : 32'sd2147483647;
    return a[31] ? -32'(signed'(w[31:0])) : 32'(signed'(w[31:0]));
  endfunction

  // int_to_fp32 returns v * 2^-sh, rounded to nearest even.
  function automatic logic [31:0] int_to_fp32(input logic signed [31:0] v,
                                              input logic [4:0]         sh);
    logic [31:0]        u;
    logic               sgn;
    int                 msb;
    logic               found;
    logic signed [10:0] e;
    logic [54:0]        norm;
    logic [23:0]        frac;
    logic               rup;
    if (v == 32'sd0) return 32'd0;
    sgn = v[31];
    u   = sgn ? 32'(-v) : 32'(v);
    msb   = 0;
    found = 1'b0;
    for (int k = 31; k >= 0; k--)
      if (!found && u[k]) begin
        found = 1'b1;
        msb   = k;
      end
    // value = u * 2^-sh, leading one at bit msb
    e    = 11'sd127 + 11'(msb) - 11'(signed'({6'd0, sh}));
    norm = {23'd0, u} << (54 - msb);        // leading one lands on bit 54
    // keep 24 significand bits, round to nearest even on the rest
    rup  = norm[30] && (|norm[29:0] || norm[31]);
    frac = norm[54:31] + 24'(rup);
    if (frac[23] == 1'b0 && rup) begin      // rounded up out of range
      frac = 24'h800000;
      e    = e + 11'sd1;
    end
    if (e <= 11'sd0)   return {sgn, 31'd0};
    if (e >= 11'sd255) return {sgn, 8'hFF, 23'd0};
    return {sgn, e[7:0], frac[22:0]};
  endfunction

  // ---------------- fixed point helpers ----------------
  function automatic logic [15:0] sat16(input logic signed [31:0] v);
    if (v >  32'sd32767)  return 16'h7FFF;
    if (v < -32'sd32768)  return 16'h8000;
    return v[15:0];
  endfunction

  // arithmetic right shift with round-half-away-from-zero, then saturate
  function automatic logic [15:0] shift_sat(input logic signed [31:0] v,
                                            input logic [4:0]         sh);
    logic signed [32:0] r;
    if (sh == 5'd0) return sat16(v);
    r = 33'(v) + (33'sd1 <<< (sh - 5'd1));
    return sat16(32'(r >>> sh));
  endfunction

endpackage

`endif
