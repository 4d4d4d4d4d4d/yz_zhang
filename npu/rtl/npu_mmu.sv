// =====================================================================
// npu_mmu.sv -- external address translation for the two memory engines.
//
// This is a region table, not a hardware page-table walker, and that is a
// decision rather than a shortcut.
//
// A walker puts an unbounded-latency memory dependency in the middle of
// the DMA address path: every AR would potentially wait on a chain of
// table reads, which have to share the same AXI port, which the data
// traffic is already saturating (MTE_IN is busy 97.6% of cycles on the
// encoder layer). The whole point of the four-layer backpressure design
// is that the time from "address generated" to "AR accepted" is bounded.
// A walker breaks that, and it buys nothing here: translation granularity
// on this device is per-tensor, not per-4-KiB-page. A descriptor names one
// contiguous window of one tensor, and a workload has a handful of live
// tensors, so eight regions programmed once per model is the whole
// requirement. If a future workload needs more than eight, the answer is
// more regions, not a walker.
//
// What the region table does buy, and what the raw physical addresses it
// replaces could not:
//   - a driver can hand the compiler a virtual layout and relocate the
//     tensors underneath it without re-emitting descriptors,
//   - a descriptor that walks off the end of its tensor faults instead of
//     silently reading someone else's memory, which is the bug class that
//     is otherwise invisible until the numbers are wrong,
//   - read-only and write-only regions, so a transposed weight tensor
//     cannot be overwritten by a mis-encoded MTE_OUT.
//
// Overlapping regions resolve to the LOWEST matching index. That makes a
// small region programmed at index 0 an override of a large one at a
// higher index, which is how a driver pins one tensor somewhere else
// without rebuilding the table.
//
// Bypass (MMU_CTRL.en = 0) is identity, but it is not unchecked: an
// address above the physical window still faults rather than being
// silently truncated to AXI_AW bits, which is what the pre-MMU design did.
// =====================================================================
`ifndef NPU_MMU_SV
`define NPU_MMU_SV

module npu_mmu
  import npu_pkg::*;
(
  input  logic                   clk,
  input  logic                   rst_n,

  // ---- CSR aperture, byte offsets inside the MMU page ----
  input  logic                   cfg_we,
  input  logic [7:0]             cfg_waddr,
  input  logic [31:0]            cfg_wdata,
  input  logic [7:0]             cfg_raddr,
  output logic [31:0]            cfg_rdata,
  // CSR.CTRL bit 0, the global "clear everything and start over". It clears
  // the fault capture for the same reason it clears ECC_FIRST: leaving a
  // stale fault address behind after STATUS.err_task has gone is worse than
  // no address at all.
  input  logic                   clr,

  // ---- lookup, port 0 = MTE_IN (reads), port 1 = MTE_OUT (writes) ----
  input  logic [1:0]             lk_req,
  input  logic [1:0][VBW-1:0]    lk_va,
  output logic [1:0][PAB_W-1:0]  lk_pa,
  output logic [1:0]             lk_fault
);
  // ---------------- region table ----------------
  logic [NRGN-1:0]            rg_v;
  logic [NRGN-1:0]            rg_r;
  logic [NRGN-1:0]            rg_w;
  logic [NRGN-1:0][VPN_W-1:0] rg_vpn;
  logic [NRGN-1:0][PPN_W-1:0] rg_ppn;
  logic [NRGN-1:0][15:0]      rg_np;    // pages, 0 => region covers nothing
  logic                       en;

  // ---------------- sticky fault capture ----------------
  logic             flt_v;
  logic [1:0]       flt_kind;
  logic             flt_port;
  logic [VBW-1:0]   flt_va;

  // ---------------- lookup ----------------
  logic [1:0]             hit;

  always_comb begin
    automatic logic [VPN_W-1:0] vpn;
    automatic logic [VPN_W-1:0] d;
    automatic logic             h;
    automatic logic             pm;
    automatic logic [PPN_W-1:0] pp;

    vpn = '0; d = '0; h = 1'b0; pm = 1'b0; pp = '0;

    for (int p = 0; p < 2; p++) begin
      vpn = lk_va[p][VBW-1:PGOW];
      h   = 1'b0;
      pm  = 1'b0;
      pp  = '0;
      if (!en) begin
        // identity: the VPN must still fit the physical window
        h  = (lk_va[p][VBW-1:PAB_W] == '0);
        pm = 1'b1;
        pp = vpn[PPN_W-1:0];
      end else begin
        // descending so that the lowest matching index wins
        for (int i = NRGN - 1; i >= 0; i--) begin
          d = vpn - rg_vpn[i];
          if (rg_v[i] && (vpn >= rg_vpn[i]) &&
              ({{(VPN_W-16){1'b0}}, rg_np[i]} > d)) begin
            h  = 1'b1;
            pm = (p == 0) ? rg_r[i] : rg_w[i];
            pp = rg_ppn[i] + PPN_W'(d);
          end
        end
      end
      hit[p]     = h;
      lk_pa[p]   = {pp, lk_va[p][PGOW-1:0]};
      lk_fault[p] = lk_req[p] && (!h || !pm);
    end
  end

  // ---------------- CSR read ----------------
  // cfg_*addr[7] = 0 : region table, four words per entry
  //                1 : global registers
  always_comb begin
    cfg_rdata = 32'd0;
    if (!cfg_raddr[7]) begin
      unique case (cfg_raddr[3:2])
        2'd0: cfg_rdata = {{(32-VPN_W){1'b0}}, rg_vpn[cfg_raddr[6:4]]};
        2'd1: cfg_rdata = {{(32-PPN_W){1'b0}}, rg_ppn[cfg_raddr[6:4]]};
        2'd2: cfg_rdata = {13'd0, rg_np[cfg_raddr[6:4]],
                           rg_w[cfg_raddr[6:4]], rg_r[cfg_raddr[6:4]],
                           rg_v[cfg_raddr[6:4]]};
        default: cfg_rdata = 32'd0;
      endcase
    end else begin
      unique case (cfg_raddr[6:2])
        5'd0:    cfg_rdata = {31'd0, en};
        5'd1:    cfg_rdata = {28'd0, flt_port, flt_kind, flt_v};
        5'd2:    cfg_rdata = {flt_va[PAB_W-1:0], 5'd0};
        5'd3:    cfg_rdata = {{(32-(VBW-PAB_W)){1'b0}}, flt_va[VBW-1:PAB_W]};
        default: cfg_rdata = 32'd0;
      endcase
    end
  end

  // ---------------- registers ----------------
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rg_v <= '0; rg_r <= '0; rg_w <= '0;
      for (int i = 0; i < NRGN; i++) begin
        rg_vpn[i] <= '0;
        rg_ppn[i] <= '0;
        rg_np[i]  <= '0;
      end
      en <= 1'b0;
      flt_v <= 1'b0; flt_kind <= MF_NONE; flt_port <= 1'b0; flt_va <= '0;
    end else begin
      if (clr) flt_v <= 1'b0;

      if (cfg_we) begin
        if (!cfg_waddr[7]) begin
          unique case (cfg_waddr[3:2])
            2'd0: rg_vpn[cfg_waddr[6:4]] <= cfg_wdata[VPN_W-1:0];
            2'd1: rg_ppn[cfg_waddr[6:4]] <= cfg_wdata[PPN_W-1:0];
            2'd2: begin
                    rg_v[cfg_waddr[6:4]]  <= cfg_wdata[0];
                    rg_r[cfg_waddr[6:4]]  <= cfg_wdata[1];
                    rg_w[cfg_waddr[6:4]]  <= cfg_wdata[2];
                    rg_np[cfg_waddr[6:4]] <= cfg_wdata[18:3];
                  end
            default: ;
          endcase
        end else begin
          unique case (cfg_waddr[6:2])
            5'd0:    en <= cfg_wdata[0];
            5'd1:    if (cfg_wdata[0]) flt_v <= 1'b0;   // write 1 to clear
            default: ;
          endcase
        end
      end

      // First fault wins: the address that started the failure is the one
      // worth keeping, not the last of the cascade behind it. An
      // acknowledgement in the same cycle as a live fault takes, and the
      // next cycle that still presents the address reports it again -- so
      // clearing the register without fixing the mapping cannot leave the
      // engine running on a translation nobody was told about.
      for (int p = 0; p < 2; p++)
        if (lk_fault[p] && !flt_v) begin
          flt_v    <= 1'b1;
          flt_kind <= hit[p] ? MF_PERM : MF_MISS;
          flt_port <= (p != 0);
          flt_va   <= lk_va[p];
        end
    end
  end

endmodule

`endif
