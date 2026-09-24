// =====================================================================
// tb_npu_prog.sv -- program-driven top-level testbench.
//
// Reads a text program: external memory image, a stream of descriptors
// with the queue and MCU port each one is pushed on, and expected
// results. This is the harness the compiler in tools/ targets, so a
// generated kernel is checked end to end through the real control plane.
//
//   run with +prog=<file>   (default tests/vectors/prog.txt)
//
// Directives
//   M <beat_hex> <64 hex>          preload one external memory beat
//   D <qid> <mcu> <64 hex>         push a descriptor
//   C <beat_hex> <64 hex>          check one external memory beat
//   X <beat_hex> <64 hex> <64 hex> check a beat under a lane mask
//   S <csr_hex> <val_hex>          check a CSR word
//   N <label>                      print a progress note
// =====================================================================
module tb_npu_prog;
  import npu_pkg::*;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;

  // ---------------- DUT ----------------
  logic [NMCU-1:0]             push_valid;
  logic [NMCU-1:0][QIDW-1:0]   push_qid;
  logic [NMCU-1:0][DESC_W-1:0] push_desc;
  logic [NMCU-1:0]             push_ready;

  logic m_arvalid, m_arready, m_rvalid, m_rready, m_rlast;
  logic [AXI_AW-1:0] m_araddr;
  logic [7:0] m_arlen; logic [2:0] m_arsize; logic [1:0] m_arburst;
  logic [AXI_IDW-1:0] m_arid, m_rid;
  logic [AXI_DW-1:0] m_rdata;
  logic m_awvalid, m_awready, m_wvalid, m_wready, m_wlast, m_bvalid, m_bready;
  logic [AXI_AW-1:0] m_awaddr;
  logic [7:0] m_awlen; logic [2:0] m_awsize; logic [1:0] m_awburst;
  logic [AXI_IDW-1:0] m_awid;
  logic [AXI_DW-1:0] m_wdata;
  logic [AXI_DW/8-1:0] m_wstrb;

  logic s_awvalid, s_awready, s_wvalid, s_wready, s_bvalid, s_bready;
  logic s_arvalid, s_arready, s_rvalid, s_rready;
  logic [LT_AW-1:0] s_awaddr, s_araddr;
  logic [MCUW-1:0]  s_awid, s_arid;
  logic [LT_DW-1:0] s_wdata, s_rdata;
  logic [LT_DW/8-1:0] s_wstrb;
  logic [1:0] s_bresp, s_rresp;

  logic qreqn = 1, qacceptn, qdeny, qactive;
  logic irq;

  npu_top u_dut (.*);

  axi_mem #(.LAT(`ifdef MEM_LAT `MEM_LAT `else 20 `endif),
            .OOO(1)) u_mem (
    .clk(clk), .rst_n(rst_n), .stall_r(1'b0),
    .arvalid(m_arvalid), .arready(m_arready), .araddr(m_araddr),
    .arlen(m_arlen), .arsize(m_arsize), .arburst(m_arburst), .arid(m_arid),
    .rvalid(m_rvalid), .rready(m_rready), .rdata(m_rdata),
    .rid(m_rid), .rlast(m_rlast),
    .awvalid(m_awvalid), .awready(m_awready), .awaddr(m_awaddr),
    .awlen(m_awlen), .awsize(m_awsize), .awburst(m_awburst), .awid(m_awid),
    .wvalid(m_wvalid), .wready(m_wready), .wdata(m_wdata),
    .wstrb(m_wstrb), .wlast(m_wlast),
    .bvalid(m_bvalid), .bready(m_bready));

  // ---------------- AXI4-Lite helpers ----------------
  task automatic csr_read(input logic [LT_AW-1:0] a,
                          input logic [MCUW-1:0]  who,
                          output logic [31:0]     d);
    @(negedge clk);
    s_arvalid = 1'b1; s_araddr = a; s_arid = who;
    @(posedge clk);
    while (!s_arready) @(posedge clk);
    @(negedge clk); s_arvalid = 1'b0; s_rready = 1'b1;
    @(posedge clk);
    while (!s_rvalid) @(posedge clk);
    d = s_rdata;
    @(negedge clk); s_rready = 1'b0;
  endtask

  task automatic csr_write(input logic [LT_AW-1:0] a,
                           input logic [MCUW-1:0]  who,
                           input logic [31:0]      d);
    @(negedge clk);
    s_awvalid = 1'b1; s_awaddr = a; s_awid = who;
    @(posedge clk);
    while (!s_awready) @(posedge clk);
    @(negedge clk); s_awvalid = 1'b0; s_wvalid = 1'b1;
    s_wdata = d; s_wstrb = '1;
    @(posedge clk);
    while (!s_wready) @(posedge clk);
    @(negedge clk); s_wvalid = 1'b0; s_bready = 1'b1;
    @(posedge clk);
    while (!s_bvalid) @(posedge clk);
    @(negedge clk); s_bready = 1'b0;
  endtask

  // ---------------- program storage ----------------
  typedef struct {
    int                qid;
    int                mcu;
    logic [DESC_W-1:0] d;
  } desc_rec;

  desc_rec           prog [$];
  int                chk_a [$];
  logic [BUS_W-1:0]  chk_d [$];
  logic [BUS_W-1:0]  chk_m [$];
  int                csr_a [$];
  logic [31:0]       csr_e [$];

  int errors = 0;

  function automatic logic [255:0] hex256(input string s);
    logic [255:0] v;
    logic [3:0]   n;
    v = '0;
    for (int i = 0; i < s.len(); i++) begin
      byte c = s[i];
      if (c >= "0" && c <= "9")      n = 4'(c - "0");
      else if (c >= "a" && c <= "f") n = 4'(c - "a" + 8'd10);
      else if (c >= "A" && c <= "F") n = 4'(c - "A" + 8'd10);
      else continue;
      v = {v[251:0], n};
    end
    return v;
  endfunction

  task automatic load(input string path);
    int           fd, code;
    string        line, kind, a1, a2, a3;
    logic [255:0] t1, t2;
    fd = $fopen(path, "r");
    if (fd == 0) begin
      $display("TEST FAILED (tb_npu_prog): cannot open %s", path);
      $finish;
    end
    while (!$feof(fd)) begin
      line = "";
      code = $fgets(line, fd);
      if (code <= 0) continue;
      if (line.len() < 2) continue;
      if (line[0] == "#") continue;
      kind = line.substr(0, 0);
      case (kind)
        "M": begin
          code = $sscanf(line, "M %s %s", a1, a2);
          if (code == 2) begin
            t1 = hex256(a1);
            t2 = hex256(a2);
            u_mem.mem[t1[$clog2(65536)-1:0]] = t2[BUS_W-1:0];
          end
        end
        "D": begin
          desc_rec r;
          code = $sscanf(line, "D %s %s %s", a1, a2, a3);
          if (code == 3) begin
            t1    = hex256(a1);
            t2    = hex256(a2);
            r.qid = int'(t1[7:0]);
            r.mcu = int'(t2[7:0]);
            t1    = hex256(a3);
            r.d   = t1[DESC_W-1:0];
            prog.push_back(r);
          end
        end
        "C": begin
          code = $sscanf(line, "C %s %s", a1, a2);
          if (code == 2) begin
            t1 = hex256(a1);
            t2 = hex256(a2);
            chk_a.push_back(int'(t1[31:0]));
            chk_d.push_back(t2[BUS_W-1:0]);
            chk_m.push_back('1);
          end
        end
        "X": begin
          code = $sscanf(line, "X %s %s %s", a1, a2, a3);
          if (code == 3) begin
            t1 = hex256(a1);
            t2 = hex256(a2);
            chk_a.push_back(int'(t1[31:0]));
            chk_d.push_back(t2[BUS_W-1:0]);
            t2 = hex256(a3);
            chk_m.push_back(t2[BUS_W-1:0]);
          end
        end
        "S": begin
          code = $sscanf(line, "S %s %s", a1, a2);
          if (code == 2) begin
            t1 = hex256(a1);
            t2 = hex256(a2);
            csr_a.push_back(int'(t1[31:0]));
            csr_e.push_back(t2[31:0]);
          end
        end
        "N": $display("  note: %s", line);
        default: ;
      endcase
    end
    $fclose(fd);
  endtask

  // ---------------- descriptor pusher ----------------
  // One process per MCU port so the submission order across cores is
  // genuinely concurrent, the way four cores driving the queue would be.
  task automatic wait_idle();
    logic [31:0] st_poll;
    forever begin
      csr_read(12'h004, 2'd0, st_poll);
      if (st_poll[4]) break;                    // STATUS.idle
    end
  endtask

  int pushed;
  task automatic push_one(input int i);
    @(negedge clk);
    push_valid       = '0;
    push_valid[prog[i].mcu] = 1'b1;
    push_qid[prog[i].mcu]   = QIDW'(prog[i].qid);
    push_desc[prog[i].mcu]  = prog[i].d;
    @(posedge clk);
    while (!push_ready[prog[i].mcu]) @(posedge clk);
    @(negedge clk);
    push_valid = '0;
    pushed++;
  endtask

  task automatic push_all();
    int idx;
    idx    = 0;
    pushed = 0;
    push_valid = '0;
    while (idx < prog.size()) begin
      // A global barrier is a full-machine fence and it costs a full
      // drain on BOTH sides. It cannot retire while anything is still in
      // the fetch path, so the driver waits for idle, submits the barrier
      // on its own, and waits again before resuming. Keeping the queues
      // fed across a global barrier would deadlock: the window fills with
      // ops fenced behind it while the descriptor it depends on is stuck
      // in a message queue. This is exactly why the queue-scope barrier
      // exists -- it fences one queue and needs no drain at all.
      if (prog[idx].d[24]) begin
        // Change the drive only on the falling edge. Clearing push_valid in
        // the same delta as the rising edge races the DUT's own sampling of
        // it and silently drops the descriptor offered that cycle.
        @(negedge clk);
        push_valid = '0;
        wait_idle();
        push_one(idx);
        idx++;
        wait_idle();
        continue;
      end

      @(negedge clk);
      for (int m = 0; m < NMCU; m++) begin
        push_valid[m] = 1'b0;
        if (idx < prog.size() && prog[idx].mcu == m && !prog[idx].d[24]) begin
          push_valid[m] = 1'b1;
          push_qid[m]   = QIDW'(prog[idx].qid);
          push_desc[m]  = prog[idx].d;
        end
      end
      @(posedge clk);
      for (int m = 0; m < NMCU; m++)
        if (push_valid[m] && push_ready[m]) begin
          idx++;
          pushed++;
        end
    end
    @(negedge clk);
    push_valid = '0;
  endtask

  // ---------------- main ----------------
  string progfile;
  logic [31:0] st, cy, iss, wf, mf, er, ew, bz;

  initial begin
    push_valid = '0; push_qid = '0; push_desc = '0;
    s_awvalid = 0; s_wvalid = 0; s_bready = 0;
    s_arvalid = 0; s_rready = 0;
    s_awaddr = 0; s_araddr = 0; s_wdata = 0; s_wstrb = '1;
    s_awid = 0; s_arid = 0;

    if (!$value$plusargs("prog=%s", progfile))
      progfile = "tests/vectors/prog.txt";

    repeat (4) @(posedge clk);
    rst_n = 1;
    repeat (2) @(posedge clk);

    load(progfile);
    $display("  program: %0d descriptors, %0d memory checks, %0d csr checks",
             prog.size(), chk_a.size(), csr_a.size());

    csr_write(12'h080, 2'd0, 32'h1);        // clear statistics

    push_all();

    // wait for the machine to drain
    begin
      int guard = 0;
      forever begin
        csr_read(12'h004, 2'd0, st);
        if (st[4]) break;                    // STATUS.idle
        guard++;
        if (guard > 200000) begin
          $display("TEST FAILED (tb_npu_prog): never went idle, STATUS=%08h", st);
          errors++;
          break;
        end
      end
    end

    // ---- error flags ----
    csr_read(12'h004, 2'd0, st);
    if (st[0]) begin errors++; $display("FAIL: err_illegal set"); end
    if (st[1]) begin errors++; $display("FAIL: err_evt_ovf set"); end
    if (st[2]) begin
      logic [31:0] et;
      csr_read(12'h020, 2'd0, et);
      errors++;
      $display("FAIL: err_task set, ERR_TAG=%08h (tag=%02h mcu=%0d pipe=%0d)",
               et, et[12:5], et[4:3], et[2:0]);
    end
    if (st[3]) begin
      logic [31:0] hs;
      csr_read(12'h024, 2'd0, hs);
      errors++;
      $display("FAIL: err_hang set, snapshot=%05h", hs[19:0]);
    end

    $display("  drained at t=%0t", $time);

    // ---- optional dump of written memory, for debugging a generator ----
    if ($test$plusargs("dumpmem"))
      for (int i = 0; i < 1024; i++)
        if (u_mem.mem[i] !== '0) $display("  mem[%0h] = %064h", i, u_mem.mem[i]);

    // ---- memory checks ----
    for (int i = 0; i < chk_a.size(); i++) begin
      logic [BUS_W-1:0] got;
      got = u_mem.mem[chk_a[i]];
      if ((got & chk_m[i]) !== (chk_d[i] & chk_m[i])) begin
        errors++;
        if (errors < 12)
          $display("FAIL beat %0h:\n  got  %064h\n  want %064h\n  mask %064h",
                   chk_a[i], got, chk_d[i], chk_m[i]);
      end
    end

    // ---- csr checks ----
    for (int i = 0; i < csr_a.size(); i++) begin
      logic [31:0] got;
      csr_read(LT_AW'(csr_a[i]), 2'd0, got);
      if (got !== csr_e[i]) begin
        errors++;
        $display("FAIL csr %03h: got %08h want %08h", csr_a[i], got, csr_e[i]);
      end
    end

    // ---- statistics ----
    csr_read(12'h00C, 2'd0, cy);
    csr_read(12'h008, 2'd0, iss);
    csr_read(12'h010, 2'd0, wf);
    csr_read(12'h014, 2'd0, mf);
    csr_read(12'h018, 2'd0, er);
    csr_read(12'h01C, 2'd0, ew);
    $display("  STATS cycles=%0d issued=%0d win_full=%0d mq_full=%0d ext_rd=%0d ext_wr=%0d",
             cy, iss, wf, mf, er, ew);
    begin
      logic [31:0] rc, wc;
      csr_read(12'h09C, 2'd0, rc);
      csr_read(12'h0A0, 2'd0, wc);
      $display("  XBAR read-conflict=%0d (%0d%%)  write-conflict=%0d (%0d%%)",
               rc, (cy == 0) ? 0 : (rc * 100) / cy,
               wc, (cy == 0) ? 0 : (wc * 100) / cy);
    end
    for (int p = 0; p < NPIPE; p++) begin
      csr_read(LT_AW'(12'h040 + 12'(p*4)), 2'd0, bz);
      $display("  BUSY[%0d]=%0d  (%0d%% of cycles)", p, bz,
               (cy == 0) ? 0 : (bz * 100) / cy);
    end

    if (errors == 0) $display("TEST PASSED (tb_npu_prog)");
    else             $display("TEST FAILED (tb_npu_prog): %0d errors", errors);
    $finish;
  end

  initial begin
    #50000000;
    $display("TEST FAILED (tb_npu_prog): global timeout");
    $finish;
  end
endmodule
