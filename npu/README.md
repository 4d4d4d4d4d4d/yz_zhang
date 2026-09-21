# A 16×16 NPU core: RTL, compiler and verification

SystemVerilog RTL for a 16×16 neural processing core, a compiler that
targets it, and a verification flow that cross-checks the two. Everything
builds and runs with Verilator 5.020 and nothing else.

```
make lint     # whole design, -Wall, zero warnings
make test     # 32 tests: lint, 4 unit testbenches, 28 generated programs
```

| | lines | contents |
|---|---|---|
| `rtl/` | 3708 | 20 modules |
| `tb/` | 1426 | 5 testbenches + an AXI4 memory model |
| `tools/` | ~1500 | ISA, bit-exact model, scheduler, three generators |
| `docs/` | ~770 | the specification |

## The machine

```
MCU ×4 ──push──> msgq (8 q × 16) ──skid──> OpSch ──credit──> 5 pipes
                                     ^                          │
                                     └────── cpl / event ───────┘
        pipes ──> read/write crossbar ──> 4 buffers (256×256b, ECC)
        MTE   <──────────────> external memory (AXI4, multi-ID, OOO)
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
16 counting semaphores, resources are per-pipe credits, and back pressure
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
- `gen_gemm.py`, `gen_encoder.py`, `gen_random.py` — kernels and a fuzzer

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

Encoder layer `S=32 d=32 d_ff=64`: 189 descriptors, 10 live events, 32
transposes, 7717 cycles, stage error against float64 between 0.31% and
2.05%.

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
the same symptom is a hang with no suspect.

**Saturating counters need a flag.** A 3-bit event counter that swallows an
eighth set is a finite-resource consequence, not a bug. A *silent* one is.
`err_evt_ovf` turns an unfindable hang into a named software error.

## Documentation

| | |
|---|---|
| `docs/spec_arch.md` | architecture, scheduling, back pressure, what is deliberately absent |
| `docs/spec_isa.md` | descriptor format, every opcode, configuration errors |
| `docs/spec_csr.md` | register map, RAS, semaphores, Q-Channel |
| `docs/spec_arith.md` | numeric semantics, measured accuracy |
| `docs/spec_layout.md` | the layout framework and why it exists |
| `docs/verification.md` | what is checked, what is not, and the bugs it found |

## Known gaps

The specification lists these; they are not oversights.

- No interrupts — completion is observed by polling `STATUS`
- No MMU; descriptors carry physical addresses
- No clock gating hierarchy or DVFS above the Q-Channel handshake
- No trace port; observability is CSR polling
- `err_hang` reports and does not recover — there is no unit-level soft
  reset, so after `err_task` software's only option is a full reset
- Crossbar arbitration conflicts are not counted
- fp16 is not supported and is not recommended: bf16 shares fp32's exponent
  range, and the measured error is dominated by the piecewise-linear
  approximations, not by mantissa width

Interrupts and unit-level soft reset are the two worth doing first.
