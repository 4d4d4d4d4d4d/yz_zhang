// ---------------------------------------------------------------------
// Real <-> IEEE-754 binary32 helpers for testbenches.
// The simulator's $shortrealtobits returns a 64-bit double pattern here,
// so the narrowing to binary32 is done explicitly below.
// ---------------------------------------------------------------------
`ifndef TB_FP_UTIL_SVH
`define TB_FP_UTIL_SVH

function automatic logic [31:0] d2f(input real r);
  logic [63:0]        d;
  logic               s;
  logic signed [12:0] e;
  logic [51:0]        m;
  logic [31:0]        top;
  logic               rnd;
  d = $realtobits(r);
  s = d[63];
  m = d[51:0];
  if (d[62:52] == 11'd0) return {s, 31'd0};
  if (d[62:52] == 11'h7FF) return (m == 52'd0) ? {s, 8'hFF, 23'd0} : 32'h7FC00000;
  e = 13'(signed'({2'b0, d[62:52]})) - 13'sd1023 + 13'sd127;
  if (e <= 13'sd0)   return {s, 31'd0};
  if (e >= 13'sd255) return {s, 8'hFF, 23'd0};
  rnd = m[28] && (|m[27:0] || m[29]);          // round to nearest even
  top = {1'b0, e[7:0], m[51:29]} + 32'(rnd);   // a carry walks into the exponent
  if (top[30:23] == 8'hFF) return {s, 8'hFF, 23'd0};
  return {s, top[30:0]};
endfunction

function automatic real f2d(input logic [31:0] f);
  logic [63:0]        d;
  logic signed [12:0] e;
  if (f[30:23] == 8'd0)    return f[31] ? -0.0 : 0.0;
  if (f[30:23] == 8'hFF)   d = {f[31], 11'h7FF, (f[22:0] != 0) ? 52'h8000000000000
                                                               : 52'd0};
  else begin
    e = 13'(signed'({5'b0, f[30:23]})) - 13'sd127 + 13'sd1023;
    d = {f[31], e[10:0], f[22:0], 29'd0};
  end
  return $bitstoreal(d);
endfunction

function automatic logic [15:0] d2bf(input real r);
  return npu_fp::fp32_to_bf16(d2f(r));
endfunction

function automatic real bf2d(input logic [15:0] b);
  return f2d({b, 16'h0000});
endfunction

function automatic real relerr(input real got, input real want);
  real d;
  if (want == 0.0) return (got == 0.0) ? 0.0 : 1.0;
  d = got - want;
  if (d < 0.0) d = -d;
  return d / ((want > 0.0) ? want : -want);
endfunction

`endif
