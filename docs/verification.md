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
| integration | `tb_ctrl` | ECC inject and reporting, read-to-acquire semaphores with owner enforcement, queue priority, all four error classes, queue barrier, Q-Channel deny/accept/gate/resume, the interrupt line and mask, and a hang-and-recover cycle driven by a memory that stops answering |
| system | `tb_npu_prog` | generated programs run on the real top level and are compared beat for beat against the bit-exact model |
| coverage | `make coverage` | line, branch and toggle coverage over the RTL, accumulated across the whole suite |

## 2. The cross-check that matters

`tools/npu_model.py` is a functional model that is bit-exact with the RTL.
Every generated program is executed by the model to produce its expected
external memory, which then becomes the check lines the RTL has to satisfy.
A disagreement anywhere — arithmetic, addressing, predication, ordering —
shows up as a failing beat.

Programs are spread across queues and MCU ports on purpose. The scheduler
may reorder anything the event graph does not pin down, so a program that
only works in submission order fails here rather than in silicon.

Current suite: 30 program tests — six random programs (three seeds × two
numeric modes), every VEC opcode swept individually, three GEMM shapes and
a full encoder layer.

## 2.1 Coverage

`make coverage` builds the testbenches instrumented and accumulates line,
branch and toggle coverage across twelve runs. Verilator's generated main
does not write coverage, so `tb/cov_main.cpp` supplies one that does.

| | covered | |
|---|---|---|
| line | 296/325 | 91% |
| branch | 385/407 | 94% |
| toggle | 11741/15879 | 73% |

The three answer different questions. Toggle coverage is reported but not
chased: a 256-bit bus that never sees every bit toggle is normal. Line and
branch are the actionable ones, and the list of unexecuted points is what
`scripts/cov_report.py` prints.

What the first run of this found, which no amount of staring at the suite
would have:

- **No generated program had ever used `rows > 1` or a non-zero intra-row
  stride.** The intra-row stride is the feature that turns a strided gather
  into one descriptor; the RTL AGU and the model's `agu()` have to walk the
  same window in the same order and nothing was checking it.
  `tools/gen_dma.py` now covers eight shapes including both.
- **Most configuration-error paths had never run.** `tb_ctrl` now drives
  twelve of them -- one per class per pipe -- and checks each raises
  `err_task`, points `ERR_TAG` at the right pipe and tag, and leaves the
  machine running.
- **A third of the CSR read mux had never been selected.** A register
  nobody reads is a register nobody has checked decodes. `tb_ctrl` now
  reads every address, including an undecoded one.

What remains uncovered is three things, and none is a test to write:

1. `ifdef NPU_DEBUG` / `NPU_TRACE` blocks, which are compiled out.
2. Unreachable fallbacks -- a `default:` arm of a fully enumerated case, a
   `return 0` after an exhaustive loop.
3. Verilator attributes the `return` statements inside an inlined
   `function automatic` to one inlining site, so a function whose every
   arm is exercised still reports arms unexecuted. That accounts for
   almost all of `npu_vec.sv`'s line gap.

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

Adding per-pipe soft reset found two more, both in the same place and both
only reachable once a unit could be reset out from under the bus:

7. **AXI IDs were re-allocated while the bus still owed responses.** A soft
   reset abandons outstanding transactions; the interconnect has not
   forgotten them. Reusing the ID immediately made a late beat from the
   abandoned burst land at the new transfer's address and count against its
   length. The ownership tracker now lives outside the unit's reset domain.
8. **A discarded beat returned an outstanding credit it never took.** The
   credit counter underflowed to its maximum, read as "no room" forever,
   and hung the very pipe the reset was supposed to recover — a recovery
   mechanism that only worked once.

Neither is exotic. Both are what happens when reset state and bus state
disagree about what is in flight, and neither is visible until you build
something that can actually hang a unit on purpose.

Tightening the encoder schedule then found three more, and the first of
them had been shipped:

9. **The single-queue event-recycling rule was unsound** and had been in
   the compiler for several commits. It assumed the issue window spans a
   bounded stretch of program order; it does not. A looser schedule
   exposed it as eleven wrong beats at the end of an encoder layer.
10. **Event assignments were not cleared between allocation attempts.**
    Inserting a barrier re-runs allocation, and the stale assignment from
    the failed attempt survived, so the emitted program was a mixture of
    two schedules. It only bit once barriers became common.
11. **The dependency analysis tracked on-chip beats only.** Any
    producer/consumer pair communicating *through external memory* -- a
    weight tile stored out and immediately streamed back in -- was
    unordered. It had been hidden by an accidental on-chip serialisation
    that the optimisation removed, and it read as zeros.

The pattern in 9 and 11 is the same: a schedule that was correct only
because it was accidentally serial. Making it faster is what proved it was
never correct.

Two more were testbench defects worth recording because they look exactly
like design bugs: a driver that cleared `push_valid` in the same delta as
the rising edge silently dropped one descriptor per occurrence, and the
first version of the global-barrier driver deadlocked by keeping the queues
fed across a fence.

## 5. Fault injection

`axi_mem` takes a `stall_r` input: while it is high the model accepts reads
and never answers them. A memory that goes away is exactly the failure a
unit-level soft reset exists for, and it is the only way to hang a pipe
without inventing a debug hook inside the design. `tb_ctrl` uses it to
drive a full cycle — hang, watchdog, snapshot naming the pipe, soft reset,
and a fresh transfer on the recovered pipe that has to complete correctly.

## 6. Measured results

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

Issue window depth, with the program regenerated for each depth so the
contract holds:

| WIN | encoder cycles | GEMM cycles | dependency stall |
|---|---|---|---|
| 8 | 6815 | 3705 | 85% |
| 16 | ~7600 | ~3900 | 87% |
| 32 | ~8000 | ~3975 | 78% |

Deeper is not better. The window being full 90% of the time reads like
"too shallow" and is not: the graph is serial, and a deeper window
lengthens the compiler's event live ranges, which buys barriers instead of
overlap.

Dependency turnaround, from `tools/gen_chain.py`: a minimal one-beat VEC op
in a chain ordered by the (pipe, queue) FIFO costs 6 cycles, of which one
is useful work. That bounds how fast any serial chain -- a softmax, a
LayerNorm -- can run.

Crossbar bank contention, now that it is counted: 0% of cycles on a blocked
GEMM, 12% on an encoder layer before VEC learned to alias a two-source op
whose B operand is the same stream as A, 9% after. The remainder is
cross-pipe and belongs to the compiler's buffer assignment.

## 7. What is not verified

Stated plainly, because a coverage claim is worth less than a list of gaps.

- **No formal properties.** The handshake checkers and the credit assertion
  are simulation-only and are not proofs.
- **No coverage metric.** There is no functional or code coverage
  collection, so "every VEC opcode is swept" means exactly that and not
  that every path inside each one is taken.
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
