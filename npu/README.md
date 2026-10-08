# A 16×16 NPU core: RTL, compiler and verification

SystemVerilog RTL for a 16×16 neural processing core, a compiler that
targets it, and a verification flow that cross-checks the two. Everything
builds and runs with Verilator 5.020 and nothing else.

```
make lint     # whole design, -Wall, zero warnings
make test     # 36 tests: lint, 5 unit testbenches, 31 generated programs
make coverage # line / branch / toggle coverage over the RTL
```

| | lines | contents |
|---|---|---|
| `rtl/` | 4342 | 21 modules |
| `tb/` | 2157 | 6 testbenches + an AXI4 memory model |
| `tools/` | 2453 | ISA, bit-exact model, scheduler, six generators |
| `docs/` | 1195 | the specification |

## The machine

```
MCU ×4 ──push──> msgq (8 q × 16) ──skid──> OpSch ──credit──> 5 pipes
                                     ^                          │
                                     └────── cpl / event ───────┘
        pipes ──> read/write crossbar ──> 4 buffers (256×256b, ECC)
        MTE   ──> MMU (8 regions) ──> external memory (AXI4, multi-ID, OOO)
        CSR   <── AXI4-Lite (counters / errors / locks / ECC inject)
        Q-Channel ──── low power quiescence handshake
```

int16×int16→int32 fixed point or bf16×bf16→fp32 float. 256-bit bus, 16
lanes, addresses in 32-byte beats.

| Pipe | What it does |
|---|---|
| CUBE | 16×16 output-stationary outer product, 256 MAC/cycle, unbounded K |
| VEC | 16-lane SIMD: 19 opcodes including a piecewise-linear table and predicated writes |
| FIX | 16×16 tile transpose, ping-pong, full bandwidth |
| MTE_IN / MTE_OUT | 2-D strided DMA with intra-row stride, AXI4 bursts |

Ordering granularity is **(pipe, queue)**, not whole pipes. Dependencies are
32 counting semaphores, resources are per-pipe credits, and back pressure
is layered: skid buffer, pipe input credit, read-response credit,
outstanding credit.

## The compiler

`tools/` is small but it is a real compiler for this target:

- `npu_isa.py` — descriptor encoding, the contract with `rtl/npu_pkg.sv`
- `npu_model.py` — a bit-exact functional model
- `npu_sched.py` — dependency analysis, event allocation, and a static
  happens-before verifier that refuses to emit a program whose ordering
  depends on luck
- `npu_layout.py` — the ROW/SEG layout framework
- `gen_gemm.py`, `gen_encoder.py`, `gen_random.py`, `gen_dma.py`,
  `gen_mmu.py`, `gen_chain.py` — kernels, a fuzzer, an AGU stress test, a
  translated-address test and a dependency turnaround microbenchmark

The model is what closes the loop: every generated program is run through
it to produce the expected memory image, which becomes the check lines the
RTL must satisfy. Programs are spread across queues and MCU ports, so a
kernel that only works in submission order fails immediately.

## Results

GEMM `M=32 N=64 K=128`, memory latency 20 cycles, ideal 1024 cycles:

| | outstanding 2 | 4 | 8 |
|---|---|---|---|
| burst 1 | 17812 | 9366 | 9055 |
| burst 4 | 5316 | 3073 | 3038 |
| burst 16 | 2316 | 2218 | 2218 |

Encoder layer `S=32 d=32 d_ff=64`: 196 descriptors, 32 transposes, 6815
cycles, stage error against float64 between 0.31% and 2.05%. 85% of those
cycles are stalled on a dependency and 0% on ordering, and a deeper issue
window makes it slightly worse rather than better.

## What the work actually taught

**The bottleneck changes kind every time you remove one.** Back pressure,
then scheduling, then layout, then the dependency chain, then bandwidth.
Each one is a different sort of problem and the previous round's intuition
does not transfer. On the encoder layer today no pipe is above 39% busy and
the window is full 93% of the time: the limit is the dependency graph.

**Layout is where an NPU compiler's complexity lives, not scheduling.**
Scheduling is regular and reusable. Layout has to be recomputed per network
and per shape, and it can generate more work than the computation. A matrix
multiply consumes its left operand transposed and produces its result
untransposed; a row reduction wants the opposite. Those two facts force a
transpose at every boundary where the orientation flips — 17% of the
encoder layer's descriptors. Moving the same GEMM data from row-major to
tile-major order, changing nothing else, was worth 3.3×.

**Burst length and outstanding depth substitute for each other.** What has
to cover the memory latency is their product. A zero-latency memory model
systematically overstates bandwidth and hides both knobs — it compresses an
8× spread to 2.4× and reorders the corners.

**A 16×16 tile has arithmetic intensity 8 against a hardware balance point
of 16,** so on paper it is a factor of two short. Keeping one operand
resident closes it: traffic becomes (1 + 1/nt) beats per MAC cycle. Adding
MAC units would not have helped; more accumulators would.

**Observability is a feature, not instrumentation.** The one cross-core
deadlock in this design reported itself as `err_hang = 1` with an all-zero
in-flight snapshot — every pipe idle and the machine still not moving,
which points at the scheduler rather than at any unit. Without the snapshot
the same symptom is a hang with no suspect. The same thing happened again
with bank contention: adding one counter turned an unexplained cycle count
into "12% of the encoder layer, and here is the instruction pattern
causing it".

**Coverage finds the tests you did not think to write.** The suite swept
every VEC opcode and every GEMM shape and still had never once used a
multi-row DMA or an intra-row stride — a headline feature with no test
behind it. "Every opcode is swept" says nothing about whether every path
inside each one is taken, and only a number distinguishes the two.

**A schedule that only works because it is accidentally serial is not a
working schedule.** Two of the compiler's dependency rules were wrong and
both had been passing tests for commits: an event-recycling distance rule
that assumed the issue window spans a bounded stretch of program order,
and a dependency analysis that tracked on-chip buffers but not external
memory. Neither was reachable until the schedule got tight enough to
reorder the pair that mattered. Optimising is how you find out whether you
were ever correct.

**Counting semaphores carry no identity.** A consumer that finds its event
non-zero cannot tell whose set it is taking. Every cheap rule for reusing
an event turns out to be unsound for that one reason, including one that
is circular in a way that takes a while to see. The sound rule needs a
full drain, which is why the event file is 32 wide rather than 16 — the
answer to running out of events is more events.

**Recovery is where reset state and bus state disagree.** Per-pipe soft
reset is three lines of intent and two real bugs. A unit that is reset has
forgotten its outstanding AXI transactions; the interconnect has not. Reuse
an ID too early and a late beat lands in the new transfer. Let a discarded
beat return an outstanding credit and the counter underflows, reads as "no
room" forever, and hangs the very pipe the reset was meant to recover.

**Translation is a per-tensor problem, not a per-page one.** A hardware
page-table walker would put an unbounded-latency memory dependency in the
middle of the DMA address path — sharing the AXI port the data traffic
already saturates — to solve a problem this device does not have. A
descriptor names one contiguous window of one tensor, and a workload has a
handful of live tensors, so eight software-programmed regions is the whole
requirement. What the regions actually buy is not relocation but *bounds*:
a descriptor that walks off the end of its tensor now faults instead of
silently reading someone else's memory, which is the bug class that is
otherwise invisible until the numbers are wrong.

**A new way for an operation to end finds the places that assumed the old
one.** Nothing before translation could abort a transfer part way through:
a configuration error is caught before the address walk starts, and
everything else runs the walk to completion. So the address generator had
no abort, and a faulted walk stayed live for exactly one cycle against the
*next* descriptor's geometry. It came out as a 256-beat AXI burst to a
nonsense address. The feature was fifteen minutes; its interaction with
state that had never needed to be torn down was the rest.

**Saturating counters need a flag.** A 3-bit event counter that swallows an
eighth set is a finite-resource consequence, not a bug. A *silent* one is.
`err_evt_ovf` turns an unfindable hang into a named software error.

## Documentation

| | |
|---|---|
| `docs/spec_arch.md` | architecture, scheduling, back pressure, what is deliberately absent |
| `docs/spec_isa.md` | descriptor format, every opcode, configuration errors |
| `docs/spec_csr.md` | register map, address translation, RAS, semaphores, Q-Channel |
| `docs/spec_arith.md` | numeric semantics, measured accuracy |
| `docs/spec_layout.md` | the layout framework and why it exists |
| `docs/verification.md` | what is checked, what is not, and the bugs it found |

## Coverage

92% line, 96% branch, 71% toggle over the RTL, accumulated across the
suite. The first run found: no program had ever used a multi-row DMA or a
non-zero intra-row stride, most configuration-error paths had never run,
and a third of the CSR read mux had never been selected. The second, after
address translation: each memory engine validates its own descriptor and
every rejection class had been driven into only one of the two, the control
slave's AXI4-Lite wait states were unreachable from the suite, and no test
had checked that a write to a reserved offset is a no-op — which in a
region table is the difference between a harmless write and a corrupted
live mapping. All of those are covered now; `npu_mmu.sv` and `npu_csr.sv`
are at 100% branch. What is left is debug blocks that compile out,
unreachable `default` arms, and two Verilator attribution artifacts, both
written down in `docs/verification.md` rather than papered over.

## Known gaps

The specification lists these; they are not oversights.

- No page-table walker. Translation is eight software-programmed regions,
  which is a decision rather than a gap — but it means no demand paging and
  no TLB coherence story
- No clock gating hierarchy or DVFS above the Q-Channel handshake
- No trace port; observability is CSR polling and the interrupt line
- Nothing triggers recovery automatically: `err_hang` reports and
  `SOFT_RST` recovers, but a supervisor has to decide
- fp16 is not supported and is not recommended: bf16 shares fp32's exponent
  range, and the measured error is dominated by the piecewise-linear
  approximations, not by mantissa width
