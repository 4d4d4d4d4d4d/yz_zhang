// =====================================================================
// npu_csr.sv -- AXI4-Lite control and status.
//
// The control plane is a separate bus from the data plane on purpose: a
// configuration read must not queue behind a 16-beat burst of activations.
// Single cycle, no burst, no ID reordering.
//
// The performance counters are not decoration. "MAC utilisation 68%,
// MTE_IN busy 97.6% of all cycles" is read directly out of BUSY[i] and
// EXT_RD; without them the only available answer is a guess.
//
// LOCK[i] is read-to-acquire. Acquisition has to complete inside one bus
// transaction or two cores both observe "free" -- for cores with no atomic
// instruction this is the only mutual exclusion primitive available. The
// owner is taken from ARID, which the interconnect drives, so a non-owner
// cannot release someone else's lock.
// =====================================================================
`ifndef NPU_CSR_SV
`define NPU_CSR_SV

module npu_csr
  import npu_pkg::*;
(
  input  logic                clk,
  input  logic                rst_n,

  // ---- AXI4-Lite slave ----
  input  logic                awvalid,
  output logic                awready,
  input  logic [LT_AW-1:0]    awaddr,
  input  logic [MCUW-1:0]     awid,
  input  logic                wvalid,
  output logic                wready,
  input  logic [LT_DW-1:0]    wdata,
  input  logic [LT_DW/8-1:0]  wstrb,
  output logic                bvalid,
  input  logic                bready,
  output logic [1:0]          bresp,
  input  logic                arvalid,
  output logic                arready,
  input  logic [LT_AW-1:0]    araddr,
  input  logic [MCUW-1:0]     arid,
  output logic                rvalid,
  input  logic                rready,
  output logic [LT_DW-1:0]    rdata,
  output logic [1:0]          rresp,

  // ---- status in ----
  input  logic                idle,
  input  logic                err_illegal,
  input  logic                err_task,
  input  logic                err_hang,
  input  logic                err_evt_ovf,
  input  logic [19:0]         hang_snapshot,
  input  logic [TAG_W+MCUW+PIPEW-1:0] err_tag,
  input  logic [31:0]         stat_issued,
  input  logic                stat_win_full,
  input  logic                stat_mq_full,
  input  logic                ext_rd_busy,
  input  logic                ext_wr_busy,
  input  logic [NPIPE-1:0]    pipe_busy,
  input  logic                ecc_ce,
  input  logic                ecc_ue,
  input  logic [BUFIDW+BUF_AW-1:0] ecc_loc,

  // ---- control out ----
  output logic                clr_stat,
  output logic [NQ-1:0]       qprio,
  output logic [1:0]          ecc_inj,
  output logic [BUFIDW-1:0]   ecc_inj_buf
);

  parameter logic [31:0] MAGIC = 32'h4E50_5501;   // "NPU" + version 1

  logic [31:0] cyc, win_full, mq_full, ext_rd, ext_wr;
  logic [31:0] busy_c [NPIPE];
  logic [31:0] ce_cnt, ue_cnt;
  logic [BUFIDW+BUF_AW-1:0] ecc_first;
  logic        ecc_first_v;
  logic [NLOCK-1:0]            lock_held;
  logic [NLOCK-1:0][MCUW-1:0]  lock_owner;

  // ------------------------------------------------ write channel
  typedef enum logic [1:0] {W_ADDR, W_DATA, W_RESP} wst_e;
  wst_e wst;
  logic [LT_AW-1:0] waddr_q;
  logic [MCUW-1:0]  wid_q;

  assign awready = (wst == W_ADDR);
  assign wready  = (wst == W_DATA);
  assign bvalid  = (wst == W_RESP);
  assign bresp   = 2'b00;

  // CSR writes are whole words: a partial strobe is accepted on the bus but
  // changes nothing, rather than silently updating part of a control field.
  logic        do_wr;
  logic [11:0] wa;
  assign do_wr = (wst == W_DATA) && wvalid && (&wstrb);
  assign wa    = waddr_q;

  // ------------------------------------------------ read channel
  logic              rpend;
  logic [31:0]       rdata_q;

  assign arready = !rpend;
  assign rvalid  = rpend;
  assign rdata   = rdata_q;
  assign rresp   = 2'b00;

  // read-to-acquire evaluated combinationally on the accepted AR
  logic        lock_rd;
  logic [2:0]  lock_idx;
  assign lock_rd  = arvalid && arready && (araddr[11:8] == 4'h1);
  assign lock_idx = araddr[4:2];

  logic [31:0] rd_mux;
  always_comb begin
    rd_mux = 32'd0;
    if (araddr[11:8] == 4'h1) begin
      // bit0: the reader now owns it. bit16: held by someone. bits 9:8 owner.
      rd_mux = {15'd0, lock_held[lock_idx],
                6'd0, lock_owner[lock_idx],
                7'd0, ~lock_held[lock_idx]};
    end else begin
      unique casez (araddr[7:0])
        8'h00:   rd_mux = MAGIC;
        8'h04:   rd_mux = {27'd0, idle, err_hang, err_task,
                           err_evt_ovf, err_illegal};
        8'h08:   rd_mux = stat_issued;
        8'h0C:   rd_mux = cyc;
        8'h10:   rd_mux = win_full;
        8'h14:   rd_mux = mq_full;
        8'h18:   rd_mux = ext_rd;
        8'h1C:   rd_mux = ext_wr;
        8'h20:   rd_mux = {19'd0, err_tag};
        8'h24:   rd_mux = {12'd0, hang_snapshot};
        8'h40,
        8'h44,
        8'h48,
        8'h4C,
        8'h50:   rd_mux = busy_c[araddr[4:2]];
        8'h84:   rd_mux = {24'd0, qprio};
        8'h88:   rd_mux = {26'd0, ecc_inj_buf, 2'd0, ecc_inj};
        8'h8C:   rd_mux = ce_cnt;
        8'h90:   rd_mux = ue_cnt;
        8'h94:   rd_mux = {22'd0, ecc_first};
        default: rd_mux = 32'd0;
      endcase
    end
  end

  // ------------------------------------------------ registers
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wst <= W_ADDR; waddr_q <= '0; wid_q <= '0;
      rpend <= 1'b0; rdata_q <= '0;
      cyc <= '0; win_full <= '0; mq_full <= '0; ext_rd <= '0; ext_wr <= '0;
      for (int p = 0; p < NPIPE; p++) busy_c[p] <= '0;
      ce_cnt <= '0; ue_cnt <= '0; ecc_first <= '0; ecc_first_v <= 1'b0;
      qprio <= '0; ecc_inj <= '0; ecc_inj_buf <= '0; clr_stat <= 1'b0;
      lock_held <= '0;
      for (int l = 0; l < NLOCK; l++) lock_owner[l] <= '0;
    end else begin
      clr_stat <= 1'b0;

      // ---- write ----
      unique case (wst)
        W_ADDR: if (awvalid) begin
                  waddr_q <= awaddr;
                  wid_q   <= awid;
                  wst     <= W_DATA;
                end
        W_DATA: if (wvalid) wst <= W_RESP;
        W_RESP: if (bready) wst <= W_ADDR;
        default: wst <= W_ADDR;
      endcase

      if (do_wr) begin
        if (wa[11:8] == 4'h1) begin
          // release, but only by the recorded owner
          if (lock_held[wa[4:2]] && (lock_owner[wa[4:2]] == wid_q))
            lock_held[wa[4:2]] <= 1'b0;
        end else begin
          unique casez (wa[7:0])
            8'h80: if (wdata[0]) clr_stat <= 1'b1;
            8'h84: qprio <= wdata[NQ-1:0];
            8'h88: begin
                     ecc_inj     <= wdata[1:0];
                     ecc_inj_buf <= wdata[BUFIDW+3:4];
                   end
            default: ;
          endcase
        end
      end

      // ---- read ----
      if (arvalid && arready) begin
        rpend   <= 1'b1;
        rdata_q <= rd_mux;
      end else if (rpend && rready) begin
        rpend <= 1'b0;
      end

      // read-to-acquire: the grant is decided in the same transaction that
      // returned the status, so two readers cannot both see "free"
      if (lock_rd && !lock_held[lock_idx]) begin
        lock_held[lock_idx]  <= 1'b1;
        lock_owner[lock_idx] <= arid;
      end

      // ---- counters ----
      if (clr_stat) begin
        cyc <= '0; win_full <= '0; mq_full <= '0; ext_rd <= '0; ext_wr <= '0;
        ce_cnt <= '0; ue_cnt <= '0; ecc_first_v <= 1'b0;
        for (int p = 0; p < NPIPE; p++) busy_c[p] <= '0;
      end else begin
        cyc <= cyc + 32'd1;
        if (stat_win_full) win_full <= win_full + 32'd1;
        if (stat_mq_full)  mq_full  <= mq_full  + 32'd1;
        if (ext_rd_busy)   ext_rd   <= ext_rd   + 32'd1;
        if (ext_wr_busy)   ext_wr   <= ext_wr   + 32'd1;
        for (int p = 0; p < NPIPE; p++)
          if (pipe_busy[p]) busy_c[p] <= busy_c[p] + 32'd1;
        if (ecc_ce) ce_cnt <= ce_cnt + 32'd1;
        if (ecc_ue) ue_cnt <= ue_cnt + 32'd1;
        if ((ecc_ce || ecc_ue) && !ecc_first_v) begin
          ecc_first   <= ecc_loc;
          ecc_first_v <= 1'b1;
        end
      end
    end
  end

endmodule

`endif
