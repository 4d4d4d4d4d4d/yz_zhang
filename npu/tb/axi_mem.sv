// =====================================================================
// axi_mem.sv -- AXI4 slave memory model for the testbench.
//
// LAT sets the minimum response latency and OOO lets reads from different
// IDs come back interleaved and out of order, which is the case the MTE
// read engine has to survive. A zero-latency, in-order model hides both
// the burst-length and the outstanding-depth effects entirely -- it makes
// every configuration look equally good.
// =====================================================================
/* verilator lint_off SYNCASYNCNET */
module axi_mem #(
  parameter int AW   = 32,
  parameter int DW   = 256,
  parameter int IDW  = 2,
  parameter int WORDS= 65536,     // beats
  parameter int LAT  = 20,
  parameter bit OOO  = 1
) (
  input  logic          clk,
  input  logic          rst_n,

  input  logic          arvalid,
  output logic          arready,
  input  logic [AW-1:0] araddr,
  input  logic [7:0]    arlen,
  input  logic [2:0]    arsize,
  input  logic [1:0]    arburst,
  input  logic [IDW-1:0] arid,
  output logic          rvalid,
  input  logic          rready,
  output logic [DW-1:0] rdata,
  output logic [IDW-1:0] rid,
  output logic          rlast,

  input  logic          awvalid,
  output logic          awready,
  input  logic [AW-1:0] awaddr,
  /* verilator lint_off UNUSEDSIGNAL */
  input  logic [7:0]    awlen,   // burst end is taken from wlast
  /* verilator lint_on UNUSEDSIGNAL */
  input  logic [2:0]    awsize,
  input  logic [1:0]    awburst,
  /* verilator lint_off UNUSEDSIGNAL */
  input  logic [IDW-1:0] awid,   // writes use a single ID; B carries no id here
  /* verilator lint_on UNUSEDSIGNAL */
  input  logic          wvalid,
  output logic          wready,
  input  logic [DW-1:0] wdata,
  input  logic [DW/8-1:0] wstrb,
  input  logic          wlast,
  output logic          bvalid,
  input  logic          bready
);
  localparam int NSLOT = 1 << IDW;
  localparam int BB    = DW / 8;        // bytes per beat

  logic [DW-1:0] mem [WORDS];

  // ---------------- read slots ----------------
  logic [NSLOT-1:0]        sv;
  logic [NSLOT-1:0][31:0]  sbeat;       // next beat address
  logic [NSLOT-1:0][8:0]   sleft;
  logic [NSLOT-1:0][IDW-1:0] sid;
  logic [NSLOT-1:0][15:0]  sdly;

  logic        free_any;
  logic [IDW-1:0] free_i;
  always_comb begin
    free_any = 1'b0;
    free_i   = '0;
    for (int i = NSLOT - 1; i >= 0; i--)
      if (!sv[i]) begin
        free_any = 1'b1;
        free_i   = IDW'(i);
      end
  end
  assign arready = free_any;

  // choose which ready slot gets to send a beat
  logic        rsel_v;
  logic [IDW-1:0] rsel;
  logic [IDW-1:0] rrot;
  always_comb begin
    automatic int idx;
    rsel_v = 1'b0;
    rsel   = '0;
    for (int k = 0; k < NSLOT; k++) begin
      idx = (k + int'(rrot)) % NSLOT;
      if (!rsel_v && sv[idx] && (sdly[idx] == 16'd0)) begin
        rsel_v = 1'b1;
        rsel   = IDW'(idx);
      end
    end
  end

  assign rvalid = rsel_v;
  assign rdata  = rsel_v ? mem[sbeat[rsel][$clog2(WORDS)-1:0]] : '0;
  assign rid    = sid[rsel];
  assign rlast  = rsel_v && (sleft[rsel] == 9'd1);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      sv <= '0; rrot <= '0;
      for (int i = 0; i < NSLOT; i++) begin
        sbeat[i] <= '0; sleft[i] <= '0; sid[i] <= '0; sdly[i] <= '0;
      end
    end else begin
      for (int i = 0; i < NSLOT; i++)
        if (sv[i] && sdly[i] != 16'd0) sdly[i] <= sdly[i] - 16'd1;

      if (arvalid && arready) begin
        sv[free_i]    <= 1'b1;
        sbeat[free_i] <= araddr / BB;
        sleft[free_i] <= 9'(arlen) + 9'd1;
        sid[free_i]   <= arid;
        sdly[free_i]  <= 16'(LAT) + (OOO ? 16'($urandom_range(0, 7)) : 16'd0);
      end

      if (rvalid && rready) begin
        sbeat[rsel] <= sbeat[rsel] + 32'd1;
        sleft[rsel] <= sleft[rsel] - 9'd1;
        if (sleft[rsel] == 9'd1) sv[rsel] <= 1'b0;
        if (OOO) begin
          // rotate so a different ID gets priority on the next beat: bursts
          // from different IDs come back interleaved and out of order, which
          // is the case the read engine has to survive
          rrot <= IDW'((int'(rrot) + 1) % NSLOT);
        end
      end
    end
  end

  // ---------------- write ----------------
  typedef enum logic [1:0] {WA, WD, WB} wst_e;
  wst_e  wst;
  logic [31:0] wbeat;
  logic [15:0] wdly;

  assign awready = (wst == WA);
  assign wready  = (wst == WD);
  assign bvalid  = (wst == WB) && (wdly == 16'd0);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wst <= WA; wbeat <= '0; wdly <= '0;
    end else begin
      unique case (wst)
        WA: if (awvalid) begin
              wbeat <= awaddr / BB;
              wst   <= WD;
            end
        WD: if (wvalid) begin
`ifdef NPU_DEBUG
              $display("[mem] t=%0t write beat=%0h data=%064h last=%0d",
                       $time, wbeat, wdata, wlast);
`endif
              for (int b = 0; b < BB; b++)
                if (wstrb[b])
                  mem[wbeat[$clog2(WORDS)-1:0]][b*8 +: 8] <= wdata[b*8 +: 8];
              wbeat <= wbeat + 32'd1;
              if (wlast) begin
                wst  <= WB;
                wdly <= 16'(LAT);
              end
            end
        WB: if (wdly != 16'd0) wdly <= wdly - 16'd1;
            else if (bready)   wst  <= WA;
        default: wst <= WA;
      endcase
    end
  end

`ifndef SYNTHESIS
  // The model only implements what the MTE is allowed to emit.
  always_ff @(posedge clk)
    if (rst_n) begin
      if (arvalid && arready && (arburst !== 2'b01 || arsize !== 3'd5)) begin
        $display("%%Error: axi_mem: unsupported AR burst/size"); $stop;
      end
      if (awvalid && awready && (awburst !== 2'b01 || awsize !== 3'd5)) begin
        $display("%%Error: axi_mem: unsupported AW burst/size"); $stop;
      end
    end
`endif
endmodule
/* verilator lint_on SYNCASYNCNET */
