// =====================================================================
// npu_opsched.sv -- in-order fetch, out-of-order issue.
//
//   msgq -> skid -> [ WIN-deep compressing window ] -> up to NPIPE issues
//
// Ordering granularity is (pipe, queue), NOT whole pipes. Two ops in
// different queues heading for the same pipe may issue in either order;
// two ops in the same queue heading for the same pipe may not. Blocking a
// whole pipe on its oldest op is what deadlocks a multi-core workload:
// core A's CUBE op waiting on an event that core B's CUBE op -- sitting
// behind it in the same pipe -- is supposed to set.
//
// Three independent admission checks per candidate:
//   dependency : counting semaphores (wait_mask, consumed at issue)
//   resource   : per-pipe credits (a local counter, no combinational
//                path into the execution unit)
//   ordering   : (pipe,queue) predecessor scan + the two barrier scopes
//
// At most one op per cycle may consume any given event bit: candidates
// whose wait_mask overlaps one already granted this cycle are held back.
// =====================================================================
`ifndef NPU_OPSCHED_SV
`define NPU_OPSCHED_SV

module npu_opsched
  import npu_pkg::*;
#(
  parameter int HANG_LIMIT = 4096
) (
  input  logic                        clk,
  input  logic                        rst_n,
  input  logic                        clr_stat,

  // ---- ingress (post skid) ----
  input  logic                        in_valid,
  input  logic [DESC_W-1:0]           in_desc,
  input  logic [QIDW-1:0]             in_qid,
  input  logic [MCUW-1:0]             in_mcu,
  output logic                        in_ready,

  // ---- semaphores ----
  input  logic [NEVT-1:0]             evt_nz,
  output logic                        cons_en,
  output logic [NEVT-1:0]             cons_mask,

  // ---- issue ports ----
  output logic [NPIPE-1:0]            iss_valid,
  output op_t  [NPIPE-1:0]            iss_op,

  // ---- completions ----
  input  logic [NPIPE-1:0]            cpl_valid,
  input  cpl_t [NPIPE-1:0]            cpl,

  // ---- status / statistics ----
  output logic                        idle,
  output logic [31:0]                 stat_issued,
  output logic                        stat_win_full,
  output logic                        err_illegal,
  output logic                        err_task,
  output logic                        err_hang,
  output logic [19:0]                 hang_snapshot,
  output logic [TAG_W+MCUW+PIPEW-1:0] err_tag,
  output logic [NPIPE-1:0][3:0]       inflight_pipe
);

  localparam int WCW = $clog2(WIN + 1);
  localparam int WIW = $clog2(WIN);
  localparam int IFW = 6;                    // per-queue in-flight width

  op_t             win   [WIN];
  logic [WIN-1:0]  wv;
  logic [WCW-1:0]  wcnt;

  logic [CRDW-1:0] credit [NPIPE];
  logic [IFW-1:0]  ifq    [NQ];
  logic [IFW+2:0]  iftot;

  // ------------------------------------------------ decode ingress
  op_t nop;
  always_comb begin
    nop.hdr       = hdr_t'(in_desc[31:0]);
    nop.wait_mask = in_desc[47:32];
    nop.pl        = in_desc[255:64];
    nop.qid       = in_qid;
    nop.mcu       = in_mcu;
  end

  // ------------------------------------------------ issue selection
  logic [NPIPE-1:0]         sel_v;
  logic [NPIPE-1:0][WIW-1:0] sel_i;
  logic [WIN-1:0]           issued, dropped, keep;
  logic [NEVT-1:0]          taken;

  logic [WIN-1:0] legal;
  always_comb
    for (int i = 0; i < WIN; i++)
      legal[i] = win[i].hdr.vld && (win[i].hdr.pipe < PIPEW'(NPIPE));

  always_comb begin
    automatic logic [NEVT-1:0] tk;
    automatic logic            found;
    automatic logic            older_q;
    automatic logic            older_pq;
    automatic logic            any_older;
    automatic logic            ok;

    sel_v   = '0;
    sel_i   = '0;
    issued  = '0;
    dropped = '0;
    tk      = '0;
    taken   = '0;
    found   = 1'b0;
    older_q = 1'b0;
    older_pq  = 1'b0;
    any_older = 1'b0;
    ok        = 1'b0;

    // an illegal op is discarded, never executed -- but only once it is
    // the oldest of its queue, so queue order is still respected
    for (int i = 0; i < WIN; i++) begin
      older_q = 1'b0;
      for (int j = 0; j < WIN; j++)
        if (j < i && wv[j] && (win[j].qid == win[i].qid)) older_q = 1'b1;
      if (wv[i] && !legal[i] && !older_q) dropped[i] = 1'b1;
    end

    for (int p = 0; p < NPIPE; p++) begin
      found = 1'b0;
      for (int i = 0; i < WIN; i++) begin
        if (!found && wv[i] && !dropped[i] && legal[i]
            && (win[i].hdr.pipe == PIPEW'(p))) begin

          // (pipe,queue) predecessor still in the window?
          older_pq  = 1'b0;
          older_q   = 1'b0;
          any_older = 1'b0;
          for (int j = 0; j < WIN; j++)
            if (j < i && wv[j]) begin
              any_older = 1'b1;
              if (!dropped[j] && (win[j].qid == win[i].qid)) begin
                older_q = 1'b1;
                if (win[j].hdr.pipe == win[i].hdr.pipe) older_pq = 1'b1;
              end
            end

          ok = !older_pq
            && (credit[p] != '0)
            && ((win[i].wait_mask & ~evt_nz) == '0)      // dependency
            && ((win[i].wait_mask &  tk)     == '0);     // one consumer/bit/cycle

          // queue-scope barrier: nothing older in this queue, anywhere
          if (win[i].hdr.bar_q)
            ok = ok && !older_q && (ifq[win[i].qid] == '0);

          // global barrier: oldest in the window and the machine is drained
          if (win[i].hdr.bar_g)
            ok = ok && !any_older && (iftot == '0);

          if (ok) begin
            found      = 1'b1;
            sel_v[p]   = 1'b1;
            sel_i[p]   = WIW'(i);
            issued[i]  = 1'b1;
            tk         = tk | win[i].wait_mask;
          end
        end
      end
    end
    taken = tk;
  end

  assign cons_mask = taken;
  assign cons_en   = |taken;

  always_comb begin
    iss_valid = sel_v;
    for (int p = 0; p < NPIPE; p++) iss_op[p] = win[sel_i[p]];
  end

  // ------------------------------------------------ window compaction
  op_t            nxt_win [WIN];
  logic [WIN-1:0] nxt_wv;
  logic [WCW-1:0] kept;
  logic           accept;

  assign keep = wv & ~issued & ~dropped;

  always_comb begin
    automatic logic [WCW-1:0] k = '0;
    for (int i = 0; i < WIN; i++) begin
      nxt_win[i] = win[i];
      nxt_wv[i]  = 1'b0;
    end
    k = '0;
    for (int i = 0; i < WIN; i++)
      if (keep[i]) begin
        nxt_win[k[WIW-1:0]] = win[i];      // k < WIN here: at most WIN keeps
        nxt_wv[k[WIW-1:0]]  = 1'b1;
        k = k + 1'b1;
      end
    kept   = k;
    accept = in_valid && (k < WCW'(WIN));
    if (accept) begin
      nxt_win[k[WIW-1:0]] = nop;
      nxt_wv[k[WIW-1:0]]  = 1'b1;
      k = k + 1'b1;
    end
    wcnt = k;
  end

  assign in_ready      = (kept < WCW'(WIN));
  assign stat_win_full = (kept == WCW'(WIN));

  // ------------------------------------------------ state update
  logic [2:0] n_iss, n_cpl;
  always_comb begin
    n_iss = '0; n_cpl = '0;
    for (int p = 0; p < NPIPE; p++) begin
      if (sel_v[p])     n_iss = n_iss + 3'd1;
      if (cpl_valid[p]) n_cpl = n_cpl + 3'd1;
    end
  end

  logic [$clog2(HANG_LIMIT+1)-1:0] hang_ctr;
  logic err_illegal_q, err_task_q, err_hang_q;
  logic [19:0] snap_q;
  logic [TAG_W+MCUW+PIPEW-1:0] errtag_q;
  logic [31:0] issued_q;

  assign err_illegal   = err_illegal_q;
  assign err_task      = err_task_q;
  assign err_hang      = err_hang_q;
  assign hang_snapshot = snap_q;
  assign err_tag       = errtag_q;
  assign stat_issued   = issued_q;
  assign idle          = (wcnt == '0) && (iftot == '0);

  always_comb
    for (int p = 0; p < NPIPE; p++)
      inflight_pipe[p] = 4'(CREDIT) - 4'(credit[p]);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int i = 0; i < WIN; i++) win[i] <= '0;
      wv <= '0;
      for (int p = 0; p < NPIPE; p++) credit[p] <= CRDW'(CREDIT);
      for (int q = 0; q < NQ; q++)    ifq[q]    <= '0;
      iftot         <= '0;
      hang_ctr      <= '0;
      err_illegal_q <= 1'b0;
      err_task_q    <= 1'b0;
      err_hang_q    <= 1'b0;
      snap_q        <= '0;
      errtag_q      <= '0;
      issued_q      <= '0;
    end else begin
      for (int i = 0; i < WIN; i++) win[i] <= nxt_win[i];
      wv <= nxt_wv;

      // credits: one issue and one completion per pipe per cycle
      for (int p = 0; p < NPIPE; p++)
        case ({sel_v[p], cpl_valid[p]})
          2'b10:   credit[p] <= credit[p] - 1'b1;
          2'b01:   credit[p] <= credit[p] + 1'b1;
          default: ;
        endcase

      // per-queue in-flight, used by the queue-scope barrier
      for (int q = 0; q < NQ; q++) begin
        automatic logic [IFW-1:0] up = '0;
        automatic logic [IFW-1:0] dn = '0;
        for (int p = 0; p < NPIPE; p++) begin
          if (sel_v[p]     && (win[sel_i[p]].qid == QIDW'(q))) up = up + 1'b1;
          if (cpl_valid[p] && (cpl[p].qid        == QIDW'(q))) dn = dn + 1'b1;
        end
        ifq[q] <= ifq[q] + up - dn;
      end
      iftot <= iftot + (IFW+3)'(n_iss) - (IFW+3)'(n_cpl);

      issued_q <= clr_stat ? '0 : issued_q + 32'(n_iss);

      // ---- error capture ----
      if (clr_stat) begin
        err_illegal_q <= 1'b0;
        err_task_q    <= 1'b0;
        err_hang_q    <= 1'b0;
      end else begin
        if (|dropped) err_illegal_q <= 1'b1;
        for (int p = 0; p < NPIPE; p++)
          if (cpl_valid[p] && cpl[p].err) begin
            err_task_q <= 1'b1;
            if (!err_task_q) errtag_q <= {cpl[p].tag, cpl[p].mcu, PIPEW'(p)};
          end
      end

      // ---- hang watchdog ----
      if ((n_iss != '0) || (n_cpl != '0) || ((wcnt == '0) && (iftot == '0))) begin
        hang_ctr <= '0;
      end else if (hang_ctr != $clog2(HANG_LIMIT+1)'(HANG_LIMIT)) begin
        hang_ctr <= hang_ctr + 1'b1;
      end else if (!err_hang_q) begin
        err_hang_q <= 1'b1;
        for (int p = 0; p < NPIPE; p++)
          snap_q[p*4 +: 4] <= 4'(CREDIT) - 4'(credit[p]);
      end
    end
  end

endmodule

`endif
