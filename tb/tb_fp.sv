// bf16 / fp32 arithmetic checked against the simulator's own IEEE doubles.
// Tolerances follow the declared semantics: bf16 carries 8 significand
// bits, so a correctly rounded bf16 result is within 2^-8 relative.
module tb_fp;
  import npu_fp::*;
`include "tb_fp_util.svh"

  int errors = 0;
  int n = 0;

  task automatic chk(input string what, input real got, input real want,
                     input real tol);
    n++;
    if (relerr(got, want) > tol) begin
      errors++;
      if (errors < 15)
        $display("FAIL %s: got %g want %g (rel %g)", what, got, want,
                 relerr(got, want));
    end
  endtask

  logic [15:0] a, b;
  logic [31:0] p, s32;
  real ra, rb;

  initial begin
    // ---- multiply is exact: bf16 x bf16 fits in an fp32 significand ----
    for (int t = 0; t < 4000; t++) begin
      a = d2bf(($urandom_range(0, 20000) / 1000.0) - 10.0);
      b = d2bf(($urandom_range(0, 20000) / 1000.0) - 10.0);
      ra = bf2d(a); rb = bf2d(b);
      p  = bf16_mul(a, b);
      chk("mul", f2d(p), ra * rb, 0.0);
    end

    // ---- add rounds once, to nearest even ----
    for (int t = 0; t < 4000; t++) begin
      a = d2bf(($urandom_range(0, 20000) / 100.0) - 100.0);
      b = d2bf(($urandom_range(0, 20000) / 100.0) - 100.0);
      ra = bf2d(a); rb = bf2d(b);
      s32 = fp32_add(d2f(ra), d2f(rb));
      if (ra + rb != 0.0)
        chk("add", f2d(s32), ra + rb, 1.0e-7);
    end

    // ---- a long fp32 accumulation, as CUBE performs it ----
    begin
      real acc_r;
      logic [31:0] acc;
      acc = 32'd0; acc_r = 0.0;
      for (int k = 0; k < 256; k++) begin
        a = d2bf(($urandom_range(0, 2000) / 1000.0) - 1.0);
        b = d2bf(($urandom_range(0, 2000) / 1000.0) - 1.0);
        acc   = fp32_add(acc, bf16_mul(a, b));
        acc_r = acc_r + bf2d(a) * bf2d(b);
      end
      chk("k=256 accumulate", f2d(acc), acc_r, 1.0e-5);
    end

    // ---- reciprocal ----
    for (int t = 0; t < 2000; t++) begin
      a  = d2bf(($urandom_range(1, 40000) / 1000.0) - 20.0);
      ra = bf2d(a);
      if (ra != 0.0)
        chk("recip", bf2d(bf16_recip(a)), 1.0 / ra, 0.005);
    end

    // ---- special values ----
    n++; if (bf16_mul(16'h0000, 16'h7F80) !== 32'h7FC00000) begin
      errors++; $display("FAIL 0*inf should be qNaN"); end
    n++; if (bf16_mul(16'h3F80, 16'h3F80) !== 32'h3F800000) begin
      errors++; $display("FAIL 1*1"); end
    n++; if (fp32_add(32'h3F800000, 32'hBF800000) !== 32'h00000000) begin
      errors++; $display("FAIL 1-1 should be +0"); end
    n++; if (bf16_recip(16'h0000) !== 16'h7F80) begin
      errors++; $display("FAIL 1/0 should be +inf"); end
    n++; if (fp32_to_bf16(32'h3F804000) !== 16'h3F80) begin
      errors++; $display("FAIL tie-to-even rounds down to 3F80"); end
    n++; if (fp32_to_bf16(32'h3F81C000) !== 16'h3F82) begin
      errors++; $display("FAIL tie-to-even rounds up to 3F82"); end
    n++; if (bf16_to_fp32(16'h0041) !== 32'h00000000) begin
      errors++; $display("FAIL subnormal input must flush to zero"); end

    if (errors == 0) $display("TEST PASSED (tb_fp): %0d checks", n);
    else             $display("TEST FAILED (tb_fp): %0d/%0d errors", errors, n);
    $finish;
  end
endmodule
