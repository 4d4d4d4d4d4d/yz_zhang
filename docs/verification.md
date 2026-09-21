# Verification

Everything here runs from `make test` (`scripts/run_tests.sh`) against
Verilator 5.020. Lint is `-Wall` with no waived warning that hides a real
signal — the waiver list in `rtl/npu.vlt` is per-file and per-signal, and
every entry says why.

## 1. What is checked

| Level | Testbench | What it establishes |
|---|---|---|
| lint | `make lint` | whole design, `-Wall`, zero warnings |
| unit | `tb_ecc` | every single-bit flip in a 352-bit line is corrected with data preserved; every in-lane double flip is flagged; a cross-lane double is two independent corrections |
| unit | `tb_fp` | 14000 assertions against IEEE doubles: exact bf16 multiply, RNE addition, a 256-term accumulation, reciprocal within 0.35%, FTZ, canonical NaN, both conversions |
| unit | `tb_cube` | CUBE against a behavioural model through the real crossbar: both numeric modes, tail tiles, ReLU, a K=256 accumulator hand-off across two descriptors, address-overflow reporting, zero-length ops |
| integration | `tb_ctrl` | ECC inject and reporting, read-to-acquire semaphores with owner enforcement, queue priority, all four error classes, queue barrier, Q-Channel deny/accept/gate/resume |
| system | `tb_npu_prog` | generated programs run on the real top level and are compared beat for beat against the bit-exact model |

## 2. The cross-check that matters

`tools/npu_model.py` is a functional model that is bit-exact with the RTL.
Every generated program is executed by the model to produce its expected
external memory, which then becomes the check lines the RTL has to satisfy.
A disagreement anywhere — arithmetic, addressing, predication, ordering —
shows up as a failing beat.

Programs are spread across queues and MCU ports on purpose. The scheduler
may reorder anything the event graph does not pin down, so a program that
only works in submission order fails here rather than in silicon.

Current suite: 28 program tests — six random programs (three seeds × two
numeric modes), every VEC opcode swept individually, three GEMM shapes and
a full encoder layer.

## 3. Static verification in the compiler

`npu_sched.Builder.verify()` refuses to emit a program where a true
dependency is enforced by neither the (pipe, queue) FIFO, an event edge,
nor a barrier. That check is what turns "it passed" into "it could not have
failed for ordering reasons", and it fires before simulation.

## 4. Bugs this found

Every one of these was a real defect in the RTL or the programming model,
and all but the last two were invisible to directed tests.

1. **Event recycling was unsound.** A counting semaphore is anonymous: a
   later consumer of a recycled event, sitting in the issue window, will
   happily consume an earlier producer's set, and the true consumer hangs
   forever. Live-range colouring is not enough. Reuse now requires either a
   global barrier between the old consumer and the new producer, or — on a
   single queue, where delivery is in program order — a reuse distance of
   at least `WIN`.
2. **Barriers did not fence.** A pending barrier blocked only itself;
   younger ops issued straight past it.
3. **A global barrier cannot fence on window position alone**, because the
   message queue pops round-robin and fetch order is not program order. It
   now also requires an empty fetch path.
4. **`STATUS.idle` had a one-cycle hole**: it used the combinational next
   window count, so in the cycle an op issued the window read empty while
   the in-flight counter had not yet counted it. A descriptor parked in the
   skid buffer was missing from the term as well. Software could read
   "done" and then read a result that was never produced; the Q-Channel
   would have accepted a power-down with work in flight.
5. **VEC column broadcast used the previous beat on every 16th row** — the
   new B beat is latched at the end of the cycle it is consumed in.
6. **NaN to fixed-point conversion disagreed** between model and RTL, which
   forced the semantics to be written down rather than left implicit.

Two more were testbench defects worth recording because they look exactly
like design bugs: a driver that cleared `push_valid` in the same delta as
the rising edge silently dropped one descriptor per occurrence, and the
first version of the global-barrier driver deadlocked by keeping the queues
fed across a fence.

## 5. Measured results

GEMM, `M=32 N=64 K=128`, memory latency 20 cycles:

| | outstanding 2 | 4 | 8 |
|---|---|---|---|
| burst 1 | 17812 | 9366 | 9055 |
| burst 4 | 5316 | 3073 | 3038 |
| burst 16 | 2316 | 2218 | 2218 |

Ideal is 1024 cycles, so the corners are 6% and 46% MAC utilisation — an
8× spread from two configuration knobs. Burst length and outstanding depth
substitute for each other; the curve flattens once their product covers the
latency. The same grid against a zero-latency memory model spans 2.4×
instead of 8× and ranks the corners differently.

Encoder layer, `S=32 d=32 d_ff=64`: 189 descriptors, 10 live events, 7717
cycles, no pipe above 39% busy, issue window full 93% of the time. At this
size the limit is the dependency chain, not any one unit.

## 6. What is not verified

Stated plainly, because a coverage claim is worth less than a list of gaps.

- **No formal properties.** The handshake checkers and the credit assertion
  are simulation-only and are not proofs.
- **No coverage metric.** There is no functional or code coverage
  collection, so "every VEC opcode is swept" means exactly that and not
  that every path inside each one is taken.
- **Crossbar arbitration conflicts are not observable.** There is no
  counter for how often two requesters contend for the same bank, so the
  cost of a bad buffer assignment can only be inferred from cycle counts.
- **AXI compliance is checked only against the model's own assumptions.**
  `axi_mem` asserts on burst type and size and nothing else; there is no
  protocol-compliance IP in this repo.
- **MTE_OUT is exercised far less than MTE_IN** — the generated programs
  are read-heavy, and the write engine's single-ID ordering has not been
  stressed with back-to-back short bursts.
- **No gate-level or timing verification.** Nothing here says the design
  closes timing, and the 256-wide fp32 accumulator array in particular has
  not been through synthesis.
- **Multi-MCU contention is shallow.** Four ports are driven, but only one
  descriptor is offered at a time; simultaneous pushes from all four ports
  are not exercised.
