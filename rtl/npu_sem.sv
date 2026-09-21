// =====================================================================
// npu_sem.sv -- NEVT counting semaphores, EVT_W bits each, saturating.
//
// A saturating counter is a finite resource: if software issues more
// set_evt than wait_mask consumes, the surplus is silently swallowed and
// a later wait hangs forever. That is unavoidable; what is NOT acceptable
// is that it hangs silently. ovf is a sticky flag that turns the software
// bug into an observable event (CSR STATUS.err_evt_ovf).
// =====================================================================
`ifndef NPU_SEM_SV
`define NPU_SEM_SV

module npu_sem
  import npu_pkg::*;
(
  input  logic                    clk,
  input  logic                    rst_n,
  input  logic                    clr,

  // consume: one issue per cycle may decrement a whole mask
  input  logic                    cons_en,
  input  logic [NEVT-1:0]         cons_mask,

  // produce: up to NPIPE completions per cycle may target the same event
  input  logic [NPIPE-1:0]        set_en,
  input  logic [NPIPE-1:0][3:0]   set_evt,

  output logic [NEVT-1:0]         nonzero,
  output logic                    ovf
);
  localparam logic [EVT_W-1:0] EVT_MAX = {EVT_W{1'b1}};

  logic [EVT_W-1:0] cnt [NEVT];
  logic [2:0]       inc [NEVT];          // 0..NPIPE sets in one cycle
  logic             dec [NEVT];

  always_comb begin
    for (int e = 0; e < NEVT; e++) begin
      inc[e] = '0;
      for (int p = 0; p < NPIPE; p++)
        if (set_en[p] && (set_evt[p] == 4'(e))) inc[e] = inc[e] + 3'd1;
      dec[e]     = cons_en && cons_mask[e];
      nonzero[e] = (cnt[e] != '0);
    end
  end

  logic ovf_q;
  assign ovf = ovf_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      for (int e = 0; e < NEVT; e++) cnt[e] <= '0;
      ovf_q <= 1'b0;
    end else if (clr) begin
      for (int e = 0; e < NEVT; e++) cnt[e] <= '0;
      ovf_q <= 1'b0;
    end else begin
      for (int e = 0; e < NEVT; e++) begin
        automatic logic signed [5:0] nxt =
            6'(signed'({1'b0, cnt[e]})) + 6'(signed'({3'b0, inc[e]}))
          - 6'(signed'({5'b0, dec[e]}));
        if (nxt > 6'(signed'({1'b0, EVT_MAX}))) begin
          cnt[e] <= EVT_MAX;
          ovf_q  <= 1'b1;                 // sticky: a set was swallowed
        end else if (nxt < 6'sd0) begin
          cnt[e] <= '0;                   // cannot happen: guarded by wait
        end else begin
          cnt[e] <= EVT_W'(nxt);
        end
      end
    end
  end

endmodule

`endif
