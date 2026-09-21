// =====================================================================
// npu_prim.sv -- reusable primitives: skid buffer, FIFO, round-robin
//                arbiter, protocol checker
// =====================================================================
`ifndef NPU_PRIM_SV
`define NPU_PRIM_SV

// ---------------------------------------------------------------------
// npu_skid : full-throughput, no-combinational-path elastic buffer.
// Cuts the ready path: s_ready is registered, so a downstream ready that
// depends on deep logic never reaches back into the upstream producer.
// ---------------------------------------------------------------------
module npu_skid #(parameter int W = 8) (
  input  logic          clk,
  input  logic          rst_n,
  input  logic          s_valid,
  output logic          s_ready,
  input  logic [W-1:0]  s_data,
  output logic          m_valid,
  input  logic          m_ready,
  output logic [W-1:0]  m_data
);
  logic          buf_v;
  logic [W-1:0]  buf_d;
  logic          out_v;
  logic [W-1:0]  out_d;

  assign s_ready = ~buf_v;
  assign m_valid = out_v;
  assign m_data  = out_d;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      buf_v <= 1'b0;
      out_v <= 1'b0;
      buf_d <= '0;
      out_d <= '0;
    end else begin
      if (out_v && m_ready) out_v <= 1'b0;
      // fill the output register whenever it is (or is becoming) free
      if (!out_v || m_ready) begin
        if (buf_v) begin
          out_d <= buf_d;
          out_v <= 1'b1;
          buf_v <= 1'b0;
        end else if (s_valid && s_ready) begin
          out_d <= s_data;
          out_v <= 1'b1;
        end
      end else if (s_valid && s_ready) begin
        // output busy -> park one beat in the skid slot
        buf_d <= s_data;
        buf_v <= 1'b1;
      end
    end
  end
endmodule

// ---------------------------------------------------------------------
// npu_fifo : synchronous FIFO. When SAFE=0 the caller guarantees (by
// credit) that no overflow can happen and the push path carries no ready.
// ---------------------------------------------------------------------
module npu_fifo #(
  parameter int W = 8,
  parameter int D = 4
) (
  input  logic          clk,
  input  logic          rst_n,
  input  logic          push,
  input  logic [W-1:0]  wdata,
  output logic          full,
  input  logic          pop,
  output logic [W-1:0]  rdata,
  output logic          empty,
  output logic [$clog2(D+1)-1:0] count
);
  localparam int AW = (D > 1) ? $clog2(D) : 1;
  logic [W-1:0] mem [D];
  logic [AW-1:0] wp, rp;
  logic [$clog2(D+1)-1:0] cnt;

  assign empty = (cnt == '0);
  assign full  = (cnt == D[$clog2(D+1)-1:0]);
  assign count = cnt;
  assign rdata = mem[rp];

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wp <= '0; rp <= '0; cnt <= '0;
    end else begin
      if (push) begin
        mem[wp] <= wdata;
        wp <= (D > 1) ? ((wp == AW'(D-1)) ? '0 : wp + 1'b1) : '0;
      end
      if (pop) begin
        rp <= (D > 1) ? ((rp == AW'(D-1)) ? '0 : rp + 1'b1) : '0;
      end
      case ({push, pop})
        2'b10: cnt <= cnt + 1'b1;
        2'b01: cnt <= cnt - 1'b1;
        default: ;
      endcase
    end
  end
endmodule

// ---------------------------------------------------------------------
// npu_arb_rr : round-robin arbiter, one-hot grant, no starvation.
// ---------------------------------------------------------------------
module npu_arb_rr #(parameter int N = 4) (
  input  logic          clk,
  input  logic          rst_n,
  input  logic [N-1:0]  req,
  input  logic          upd,        // advance the pointer this cycle
  output logic [N-1:0]  gnt
);
  localparam int PW = (N > 1) ? $clog2(N) : 1;
  logic [PW-1:0] ptr, sel, idx;
  logic [31:0]   sum;
  logic          found;

  always_comb begin
    gnt   = '0;
    sel   = '0;
    found = 1'b0;
    for (int unsigned i = 0; i < N; i++) begin
      sum = 32'(i) + 32'(ptr);                    // both < N, so sum < 2N
      idx = (sum >= 32'(N)) ? PW'(sum - 32'(N)) : PW'(sum);
      if (!found && req[idx]) begin
        found = 1'b1;
        sel   = idx;
      end
    end
    if (found) gnt[sel] = 1'b1;
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n)            ptr <= '0;
    else if (upd && found) ptr <= (sel == PW'(N-1)) ? '0 : sel + 1'b1;
  end
endmodule

// ---------------------------------------------------------------------
// npu_check : handshake protocol checker. Simulation only.
//   * valid must not be withdrawn before ready
//   * payload must not change while valid is held
// ---------------------------------------------------------------------
module npu_check #(
  parameter int W = 8,
  parameter string NAME = "chan"
) (
  input logic         clk,
  input logic         rst_n,
  input logic         valid,
  input logic         ready,
  input logic [W-1:0] data
);
`ifndef SYNTHESIS
  logic         v_q;
  logic         r_q;
  logic [W-1:0] d_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      v_q <= 1'b0; r_q <= 1'b0; d_q <= '0;
    end else begin
      v_q <= valid; r_q <= ready; d_q <= data;
    end
  end

  always_ff @(posedge clk) begin
    if (rst_n && v_q && !r_q) begin
      if (!valid) begin
        $display("%%Error: %s: valid withdrawn before ready at time %0t", NAME, $time);
        $stop;
      end
      if (data !== d_q) begin
        $display("%%Error: %s: payload changed while valid held at time %0t", NAME, $time);
        $stop;
      end
    end
  end
`endif
endmodule

`endif
