// Exhaustive-ish SECDED check: no error, every single-bit flip (correctable,
// data preserved), every double-bit flip (flagged uncorrectable).
module tb_ecc;
  import npu_pkg::*;

  logic [BUS_W-1:0]  din, dout;
  logic [LINE_W-1:0] line, corrupt;
  logic [LANES-1:0]  ce, ue;
  int errors = 0;

  npu_ecc_enc u_enc (.data(din),      .line(line));
  npu_ecc_dec u_dec (.line(corrupt),  .data(dout), .ce(ce), .ue(ue));

  task automatic chk(input string what, input logic cond);
    if (!cond) begin
      errors++;
      $display("FAIL: %s", what);
    end
  endtask

  initial begin
    // ---- clean path ----
    for (int t = 0; t < 200; t++) begin
      din = {$urandom, $urandom, $urandom, $urandom,
             $urandom, $urandom, $urandom, $urandom};
      #1 corrupt = line;
      #1 chk("clean data", dout === din);
      chk("clean ce", ce === '0);
      chk("clean ue", ue === '0);
    end

    // ---- every single-bit flip in lane 0..15 ----
    din = {$urandom, $urandom, $urandom, $urandom,
           $urandom, $urandom, $urandom, $urandom};
    #1;
    for (int b = 0; b < LINE_W; b++) begin
      corrupt = line;
      corrupt[b] = ~corrupt[b];
      #1;
      chk($sformatf("SEC data bit %0d", b), dout === din);
      chk($sformatf("SEC ce bit %0d", b),   ce[b/ECC_N] === 1'b1);
      chk($sformatf("SEC ue bit %0d", b),   ue === '0);
    end

    // ---- every double-bit flip inside one lane ----
    for (int i = 0; i < ECC_N; i++)
      for (int j = i + 1; j < ECC_N; j++) begin
        corrupt = line;
        corrupt[i] = ~corrupt[i];
        corrupt[j] = ~corrupt[j];
        #1;
        chk($sformatf("DED %0d,%0d", i, j), ue[0] === 1'b1);
      end

    // ---- double-bit flips spread across two lanes stay correctable ----
    corrupt = line;
    corrupt[3]          = ~corrupt[3];
    corrupt[ECC_N + 7]  = ~corrupt[ECC_N + 7];
    #1;
    chk("cross-lane double is 2x SEC", dout === din && ce[0] && ce[1] && ue === '0);

    if (errors == 0) $display("TEST PASSED (tb_ecc)");
    else             $display("TEST FAILED (tb_ecc): %0d errors", errors);
    $finish;
  end
endmodule
