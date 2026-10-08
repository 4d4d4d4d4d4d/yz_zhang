// =====================================================================
// tb_mmu.sv -- region table unit test.
//
// The program-level test (tests/vectors/mmu.txt) can only exercise the
// addresses a working program uses. Everything here is what a program must
// never do: run off the end of a tensor, write through a read-only
// mapping, use an address no region covers. Those paths are the reason the
// MMU is here at all, so they are the ones that have to be checked
// directly.
// =====================================================================
module tb_mmu;
  import npu_pkg::*;

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;

  logic        cfg_we, clr;
  logic [7:0]  cfg_waddr, cfg_raddr;
  logic [31:0] cfg_wdata, cfg_rdata;

  logic [1:0]            lk_req;
  logic [1:0][VBW-1:0]   lk_va;
  logic [1:0][PAB_W-1:0] lk_pa;
  logic [1:0]            lk_fault;

  int errors = 0;

  npu_mmu dut (
    .clk(clk), .rst_n(rst_n),
    .cfg_we(cfg_we), .cfg_waddr(cfg_waddr), .cfg_wdata(cfg_wdata),
    .cfg_raddr(cfg_raddr), .cfg_rdata(cfg_rdata), .clr(clr),
    .lk_req(lk_req), .lk_va(lk_va), .lk_pa(lk_pa), .lk_fault(lk_fault));

  task automatic chk(input string what, input logic cond);
    if (!cond) begin
      errors++;
      $display("FAIL: %s", what);
    end
  endtask

  task automatic wr(input logic [7:0] a, input logic [31:0] d);
    @(negedge clk);
    cfg_we = 1'b1; cfg_waddr = a; cfg_wdata = d;
    @(negedge clk);
    cfg_we = 1'b0;
  endtask

  task automatic rd(input logic [7:0] a, output logic [31:0] d);
    cfg_raddr = a;
    #1 d = cfg_rdata;
  endtask

  // Program one region. pages = 0 is legal and covers nothing.
  task automatic region(input int idx, input logic [VPN_W-1:0] vpn,
                        input logic [PPN_W-1:0] ppn, input logic [15:0] pages,
                        input logic v, input logic r, input logic w);
    wr(8'(16 * idx + 0), {{(32-VPN_W){1'b0}}, vpn});
    wr(8'(16 * idx + 4), {{(32-PPN_W){1'b0}}, ppn});
    wr(8'(16 * idx + 8), {13'd0, pages, w, r, v});
  endtask

  // A lookup is combinational, but the fault capture register is not, so a
  // lookup is held across one clock edge: that is the cycle in which the
  // engine would have driven AR with this address.
  task automatic look(input int port, input logic [VBW-1:0 ] va);
    @(negedge clk);
    lk_req    = '0;
    lk_va[0]  = '0;
    lk_va[1]  = '0;
    lk_req[port] = 1'b1;
    lk_va[port]  = va;
    #1;                    // combinational outputs have settled
    @(posedge clk); #1;    // ... and the capture register has taken them
  endtask

  task automatic quiet();
    @(negedge clk);
    lk_req = '0;
    #1;
    @(posedge clk); #1;
  endtask

  // Dropping the request first matters: a fault present during the clear
  // wins, which the test below checks on purpose.
  task automatic clear_fault();
    quiet();
    wr(8'h84, 32'h1);
  endtask

  // beat index of a byte address
  function automatic logic [VBW-1:0] vb(input longint unsigned byte_addr);
    return VBW'(byte_addr >> 5);
  endfunction

  logic [31:0] d;
  logic [VBW-1:0] va;

  initial begin
    cfg_we = 0; cfg_waddr = 0; cfg_wdata = 0; cfg_raddr = 0; clr = 0;
    lk_req = '0; lk_va = '0;
    repeat (3) @(posedge clk);
    rst_n = 1;
    @(negedge clk);

    // ================= bypass =================
    // Reset state is translation off, and off is identity.
    rd(8'h80, d); chk("reset: translation disabled", d[0] === 1'b0);

    look(0, vb(64'h0000_1234_5600));
    chk("bypass identity", lk_pa[0] === PAB_W'(64'h0000_1234_5600 >> 5));
    chk("bypass no fault", lk_fault[0] === 1'b0);

    // The last beat of the physical window still translates ...
    look(0, VBW'({PAB_W{1'b1}}));
    chk("bypass top of window", lk_fault[0] === 1'b0);
    // ... and the first beat above it does not. The pre-MMU design
    // truncated this silently and read some other address entirely.
    look(0, VBW'(1) << PAB_W);
    chk("bypass above window faults", lk_fault[0] === 1'b1);
    look(1, VBW'(1) << PAB_W);
    chk("bypass above window faults on write port", lk_fault[1] === 1'b1);

    // A fault is only a fault when the port is asking.
    @(negedge clk);
    lk_req = '0; lk_va[0] = VBW'(1) << PAB_W; #1;
    chk("no request, no fault", lk_fault === 2'b00);

    // The capture register took the faults above; clear it before going on.
    rd(8'h84, d);
    chk("bypass fault captured", d[0] === 1'b1);
    chk("bypass fault kind is miss", d[2:1] === MF_MISS);
    clear_fault();
    rd(8'h84, d); chk("fault cleared", d[0] === 1'b0);

    // ================= region programming =================
    //   0: 1 page  at VA 0x40_0000_2000 -> PA 0x0001_0000, read only
    //   2: 4 pages at VA 0x40_0000_0000 -> PA 0x0000_4000, read only
    //   3: 4 pages at VA 0x60_0000_0000 -> PA 0x0000_8000, write only
    //   5: valid but zero pages
    region(0, VPN_W'(64'h40_0000_2000 >> PG_SH), PPN_W'(20'h10), 16'd1,
           1'b1, 1'b1, 1'b0);
    region(2, VPN_W'(64'h40_0000_0000 >> PG_SH), PPN_W'(20'h04), 16'd4,
           1'b1, 1'b1, 1'b0);
    region(3, VPN_W'(64'h60_0000_0000 >> PG_SH), PPN_W'(20'h08), 16'd4,
           1'b1, 1'b0, 1'b1);
    region(5, VPN_W'(64'h70_0000_0000 >> PG_SH), PPN_W'(20'h20), 16'd0,
           1'b1, 1'b1, 1'b1);

    rd(8'h00, d);
    chk("readback vpn[0]", d === 32'(64'h40_0000_2000 >> PG_SH));
    rd(8'h24, d); chk("readback ppn[2]", d === 32'h4);
    rd(8'h28, d); chk("readback attr[2]", d === {13'd0, 16'd4, 1'b0, 1'b1, 1'b1});
    rd(8'h38, d); chk("readback attr[3]", d === {13'd0, 16'd4, 1'b1, 1'b0, 1'b1});
    rd(8'h0C, d); chk("entry word 3 reserved", d === 32'd0);
    rd(8'h90, d); chk("unmapped global reads 0", d === 32'd0);

    // ---- writes that must change nothing ----
    // The reserved fourth word of an entry, and a reserved global offset.
    // A decoder that fell through to a neighbouring case would corrupt a
    // live mapping, which is the sort of thing nothing else would notice.
    wr(8'h2C, 32'hFFFF_FFFF);
    rd(8'h20, d); chk("entry vpn survives a reserved write",
                      d === 32'(64'h40_0000_0000 >> PG_SH));
    rd(8'h28, d); chk("entry attr survives a reserved write",
                      d === {13'd0, 16'd4, 1'b0, 1'b1, 1'b1});
    wr(8'h90, 32'hFFFF_FFFF);
    rd(8'h80, d); chk("MMU_CTRL survives a reserved global write",
                      d[0] === 1'b0);

    // A programmed table changes nothing until translation is enabled.
    look(0, vb(64'h40_0000_0000));
    chk("still bypassed", lk_fault[0] === 1'b1);
    clear_fault();
    wr(8'h80, 32'h1);
    rd(8'h80, d); chk("translation enabled", d[0] === 1'b1);

    // ================= translation =================
    look(0, vb(64'h40_0000_0000));
    chk("page 0 maps", lk_pa[0] === PAB_W'(32'h0000_4000 >> 5));
    chk("page 0 no fault", lk_fault[0] === 1'b0);

    // page 1 of the region: ppn has to carry, the offset has to survive
    look(0, vb(64'h40_0000_1060));
    chk("page 1 maps", lk_pa[0] === PAB_W'(32'h0000_5060 >> 5));

    // page 3 is the last page of region 2
    look(0, vb(64'h40_0000_3FE0));
    chk("last page maps", lk_pa[0] === PAB_W'(32'h0000_7FE0 >> 5));
    chk("last page no fault", lk_fault[0] === 1'b0);

    // one beat past the end of the region
    look(0, vb(64'h40_0000_4000));
    chk("past the end faults", lk_fault[0] === 1'b1);
    rd(8'h84, d);
    chk("past the end is a miss", d[0] === 1'b1 && d[2:1] === MF_MISS);
    rd(8'h88, d); chk("fault VA low", d === 32'h0000_4000);
    rd(8'h8C, d); chk("fault VA high", d === 32'h40);

    // Acknowledging a fault whose cause is still live does not lose it:
    // the clear takes, and the next cycle in which the address is still
    // presented reports it again. An MCU that clears MMU_FAULT without
    // fixing the mapping therefore sees it come back rather than running
    // on with a silently broken translation.
    wr(8'h84, 32'h1);
    rd(8'h84, d); chk("acknowledgement takes", d[0] === 1'b0);
    @(posedge clk); #1;
    rd(8'h84, d); chk("a live fault re-reports", d[0] === 1'b1);
    clear_fault();
    rd(8'h84, d); chk("clear takes once the fault stops", d[0] === 1'b0);

    // ---- lowest index wins ----
    look(0, vb(64'h40_0000_2040));
    chk("index 0 overrides index 2", lk_pa[0] === PAB_W'(32'h0001_0040 >> 5));

    // ---- permissions ----
    look(1, vb(64'h40_0000_0000));
    chk("write to a read-only region faults", lk_fault[1] === 1'b1);
    rd(8'h84, d);
    chk("read-only violation is a permission fault",
        d[0] === 1'b1 && d[2:1] === MF_PERM && d[3] === 1'b1);
    clear_fault();

    look(0, vb(64'h60_0000_0000));
    chk("read of a write-only region faults", lk_fault[0] === 1'b1);
    rd(8'h84, d);
    chk("write-only violation reports the read port",
        d[0] === 1'b1 && d[2:1] === MF_PERM && d[3] === 1'b0);
    clear_fault();

    look(1, vb(64'h60_0000_2000));
    chk("write to a write-only region passes", lk_fault[1] === 1'b0);
    chk("write region maps", lk_pa[1] === PAB_W'(32'h0000_A000 >> 5));

    // ---- a valid region of zero pages covers nothing ----
    look(0, vb(64'h70_0000_0000));
    chk("zero-page region covers nothing", lk_fault[0] === 1'b1);
    clear_fault();

    // ---- first fault wins ----
    look(0, vb(64'h40_0000_4000));              // miss
    look(1, vb(64'h40_0000_0000));              // permission, one cycle later
    rd(8'h84, d);
    chk("first fault is kept", d[2:1] === MF_MISS && d[3] === 1'b0);
    rd(8'h88, d); chk("first fault VA is kept", d === 32'h0000_4000);
    clear_fault();

    // ---- both ports faulting in one cycle is still one capture ----
    @(negedge clk);
    lk_req = 2'b11;
    lk_va[0] = vb(64'h40_0000_4000);
    lk_va[1] = vb(64'h50_0000_0000);
    #1;
    chk("both ports fault", lk_fault === 2'b11);
    @(posedge clk); #1;
    quiet();
    rd(8'h84, d); chk("simultaneous faults capture once", d[0] === 1'b1);
    clear_fault();

    // ---- MMU_FAULT is write-1-to-clear, so zero is not a clear ----
    look(0, vb(64'h50_0000_0000));
    quiet();
    rd(8'h84, d); chk("fault captured for the W1C check", d[0] === 1'b1);
    wr(8'h84, 32'h0);
    rd(8'h84, d); chk("writing zero does not clear the fault", d[0] === 1'b1);
    clear_fault();

    // ---- the global counter clear also drops a stale fault ----
    look(0, vb(64'h50_0000_0000));
    quiet();
    rd(8'h84, d); chk("fault captured before the global clear", d[0] === 1'b1);
    @(negedge clk); clr = 1'b1; @(negedge clk); clr = 1'b0;
    rd(8'h84, d); chk("the global clear drops the fault", d[0] === 1'b0);

    // ---- disabling translation goes back to identity ----
    wr(8'h80, 32'h0);
    look(0, vb(64'h40_0000_0000));
    chk("disable restores identity", lk_fault[0] === 1'b1);   // VA > 32 bit

    if (errors == 0) $display("TEST PASSED (tb_mmu)");
    else             $display("TEST FAILED (tb_mmu): %0d errors", errors);
    $finish;
  end
endmodule
