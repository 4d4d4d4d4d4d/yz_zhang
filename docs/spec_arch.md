# Architecture specification

## 1. Scope

A 16×16 NPU core: five decoupled execution pipes fed by a shared issue
window, four ECC-protected on-chip buffers behind a crossbar, an AXI4
master for bulk data and an AXI4-Lite slave for control.

All numbers below are the RTL's actual parameters (`rtl/npu_pkg.sv`), not
targets.

| Parameter | Value | Note |
|---|---|---|
| `LANES` | 16 | SIMD width and systolic tile edge |
| `ELEM_W` | 16 | int16 or bf16 |
| `BUS_W` | 256 bit | one *beat*, 32 bytes |
| `ACC_W` | 32 | int32 / fp32 accumulator |
| `NBUF` × `BUF_D` | 4 × 256 beats | 32 KiB total, ECC on top |
| `NMCU` | 4 | task submission ports |
| `NQ` × `QD` | 8 × 16 | message queues |
| `NPIPE` | 5 | CUBE, VEC, FIX, MTE_IN, MTE_OUT |
| `NEVT` × `EVT_W` | 16 × 3 bit | counting semaphores, saturating |
| `WIN` | 8 | issue window depth |
| `CREDIT` | 4 | per-pipe issue credits |
| `MAX_BURST` / `NID` | 16 / 4 | build-time overridable |

## 2. Data plane

```
MCU ×4 ──push──> msgq (8 q × 16) ──skid──> OpSch ──credit──> 5 pipes
                                     ^                          │
                                     └────── cpl / event ───────┘
        pipes ──> read/write crossbar ──> 4 buffers (256×256b, ECC)
        MTE   <──────────────> external memory (AXI4, multi-ID, OOO)
        CSR   <── AXI4-Lite (counters / errors / locks / ECC inject)
        Q-Channel ──── low power quiescence handshake
```

Addresses inside the machine are in beats. An on-chip address is
`{buf[1:0], beat[7:0]}` in the low 10 bits of a 16-bit descriptor field;
external addresses are byte addresses and must be beat aligned.

## 3. Execution pipes

| Pipe | Function |
|---|---|
| **CUBE** | 16×16 output-stationary outer-product accumulate, 256 MAC/cycle. K is unbounded; `acc_cont` / `acc_hold` relay a partial sum across descriptors so K > 256 never spills. `rows`/`n_dim` cover tail tiles below 16. int16→int32 or bf16→fp32. |
| **VEC** | 16 lanes. Unary+immediate, two-source tensor, row-vector broadcast, column-scalar broadcast, row reduction, 16-segment piecewise linear table, reciprocal, static and data-dependent predicated write, bf16↔fixed conversion. |
| **FIX** | 16×16 tile transpose, ping-pong, one beat per cycle each way. |
| **MTE_IN / MTE_OUT** | 2-D strided DMA with an intra-row stride, AXI4 bursts, outstanding credit. |

### 3.1 CUBE operand shape

`C[i][j] += A[k][i] · B[k][j]` for `k = 0 .. k_len-1`. One beat of A and
one of B per cycle gives 256 MACs. Both operands must be contiguous along
k, which is the constraint the whole compiler layout scheme exists to
serve — see `spec_layout.md`.

A and B are independent crossbar requesters with their own response FIFOs.
They may desync: the array consumes a pair only when both are present. Two
operands in different banks run at full rate; two in the same bank halve
it rather than deadlocking.

### 3.2 VEC B-operand fetch modes

| Mode | Opcodes | B supply |
|---|---|---|
| none | MOV ADDI MULI MAXI RECIP CVT_* RED_* SEL | — |
| stream | ADD SUB MUL MAX MIN SELD | one beat per row |
| once | BRC_R | one beat, a row vector, held |
| column | BRC_C | one beat per 16 rows, lane = row mod 16 |
| lut | LUT | two beats: slopes then intercepts |

Row reductions pack one scalar per row into consecutive lanes and emit a
beat every 16 rows. That is what makes a reduced vector contiguous — and
what makes it the wrong orientation for CUBE.

## 4. Scheduling

Fetch is in order from the message queue through a skid buffer into an
8-deep compressing window. Up to `NPIPE` ops issue per cycle, at most one
per pipe.

**Ordering granularity is (pipe, queue), not whole pipes.** Two ops in
different queues heading for the same pipe may issue in either order; two
in the same queue heading for the same pipe may not. Blocking a whole pipe
on its oldest op deadlocks a multi-core workload: core A's CUBE op waits on
an event that core B's CUBE op, stuck behind it in the same pipe, is
supposed to set.

Three independent admission checks per candidate:

- **dependency** — every bit of `wait_mask` has a non-zero counter. The
  counters are decremented at issue, not at completion.
- **resource** — the per-pipe credit is non-zero. A credit is a local
  counter, so the issue decision has no combinational path into the
  execution unit.
- **ordering** — no (pipe, queue) predecessor still in the window, and no
  un-retired barrier ahead.

At most one op per cycle may consume any given event bit; a candidate whose
`wait_mask` overlaps one already granted this cycle waits.

### 4.1 Barriers

| Scope | Passes when | Fences |
|---|---|---|
| `bar_q` | nothing older in its queue is in the window, and that queue has nothing in flight | younger ops in the same queue |
| `bar_g` | it is the oldest op in the window, the whole machine is drained, **and the fetch path is empty** | every younger op |

The fetch-path term is what makes `bar_g` a real program-order fence.
Window position alone is not program order — the message queue pops
round-robin, so a descriptor pushed earlier on another queue can arrive
after the barrier. Software must therefore let the machine drain before
submitting a global barrier and again before resuming; the hardware simply
will not let one pass otherwise. The queue-scope barrier has no such cost,
which is why it is the one to use in an inner loop.

## 5. Back pressure, in four layers

| Layer | Problem it removes |
|---|---|
| skid buffer | cuts the combinational chain `unit ready → scheduler → msgq → MCU`. `in_ready` is a function of the entire issue-selection cone; without the skid that cone reaches the MCU write ports. |
| pipe input credit | the unit's input FIFO can never overflow, so no ready has to come back combinationally |
| read response credit | an SRAM read cannot be back-pressured, so a landing slot is reserved before the read is issued |
| outstanding credit | AR is issued only when the landing FIFO has room for the whole burst |

## 6. Out-of-order AXI returns

The read engine needs no reorder buffer. Each in-flight burst owns an AXI
ID and a destination beat address; an arriving R beat is tagged with its
own destination before it is queued, so interleaved IDs simply land in
different places. The write engine uses a single ID: AXI4 forbids
interleaving W bursts and requires W to follow AW order, so more IDs would
buy nothing and cost an ordering hazard.

## 6.1 Burst boundaries

AXI4 forbids a burst from crossing a 4 KiB boundary: a real interconnect
decodes on that boundary, so a crossing burst is not slow, it is wrong —
half of it arrives at a different slave. The address generator therefore
clips every burst to the next 4 KiB boundary in addition to `MAX_BURST`.
This is not a translation feature; it was a protocol violation whenever a
window happened to start within `MAX_BURST` beats of a page end, and no
existing program happened to do that, which is why it took a boundary
assertion in the memory model to surface. The same clip keeps a burst
inside one translation region, since a region is a whole number of pages.

## 7. Address translation

Eight software-programmed regions, each a contiguous run of 4 KiB pages,
shared by both memory engines: one register file, two combinational lookup
ports. Duplicating the table per engine would double the registers and
make every CSR write a broadcast, and the lookup has no state to arbitrate
for. Register layout and fault reporting are in `spec_csr.md` section 1.1.

**There is no hardware page-table walker, and that is a decision rather
than a simplification.** A walker puts an unbounded-latency memory
dependency in the middle of the DMA address path: every AR would
potentially wait on a chain of table reads, which have to share the AXI
port that the data traffic is already saturating — MTE_IN is busy 97.6% of
cycles on the encoder layer. The whole point of the four-layer back
pressure above is that the time from *address generated* to *AR accepted*
is bounded, and a walker breaks that.

It would also buy nothing here. Translation granularity on this device is
per-tensor, not per-page: a descriptor names one contiguous window of one
tensor, and a workload has a handful of live tensors. Eight regions
programmed once per model is the whole requirement. If a future workload
needs more than eight, the answer is more regions.

What the region table does buy, and raw physical addresses could not:

- a driver can hand the compiler a virtual layout and relocate the tensors
  underneath it without re-emitting descriptors,
- a descriptor that walks off the end of its tensor faults instead of
  silently reading someone else's memory — the bug class that is otherwise
  invisible until the numbers are wrong,
- read-only and write-only regions, so a transposed weight tensor cannot be
  overwritten by a mis-encoded MTE_OUT.

The cost in the datapath is one comparator bank and no extra cycle: the
lookup is combinational, in parallel with the arbitration that was already
deciding whether AR could go out this cycle.

One thing it changed that had nothing to do with translation. A transfer
can now end *before* the address generator runs dry, because a fault stops
it part way through. The AGU therefore needs an explicit abort: without it
the half-finished walk stayed live for the one cycle between accepting the
next descriptor and `start` landing, and presented the stale position
against the new descriptor's geometry — which showed up as a 256-beat AXI
burst to a nonsense address.

## 8. ECC

SECDED(22,16) per 16-bit lane: Hamming(21,16) plus an overall parity bit.
**ECC granularity must equal write granularity.** VEC supports lane-granular
predicated writes, so a beat write may touch an arbitrary subset of the 16
lanes; a wider code word would need a read-modify-write on the check bits
for every predicated store. 16+6 costs 37.5%; widening to 64-bit data would
cost 12.5% and reintroduce RMW.

Single-bit errors are corrected transparently and counted. Double-bit
errors are flagged uncorrectable. The first error's `{buffer, beat}` is
latched. `CSR.ECCINJ` flips one or two bits on write into a chosen bank so
the path can be exercised from software.

## 9. What is deliberately not here

Honest list; each of these is real work in a production SoC.

- **Demand paging.** Translation is eight software-programmed regions and
  nothing else: no page-table walker, no TLB fill, no faulting-and-retry.
  Section 7 argues that is the right trade for this device, but it does
  mean every page a descriptor touches has to be mapped before it runs.
- **Clock gating / DVFS.** The Q-Channel reaches quiescence; there is no
  ICG hierarchy and no voltage/frequency control.
- **Debug / trace port.** Observability is CSR polling only; there is no
  CoreSight-style trace output.
- **AXI QoS.** Queue priority is not forwarded to `AxQOS`.
- **Watchdog timeout policy.** `err_hang` reports and a soft reset
  recovers, but nothing triggers that recovery automatically; a supervisor
  has to decide.

Interrupts (`IRQ_STATUS` / `IRQ_ENABLE`), per-pipe soft reset
(`SOFT_RST`) and address translation (section 7) were the gaps worth
closing first and all three are now implemented. In each case the
interesting part was not the feature. For the soft reset it was what a
reset does to state the bus still remembers; for translation it was that a
transfer can now end before its address walk does.

## 10. Observability of bank contention

`XBAR_RCONF` / `XBAR_WCONF` count cycles in which a requester asked for a
bank and was refused. This is the direct cost of a buffer assignment that
puts two live operands in the same bank, and it is not otherwise visible —
it shows up only as an unexplained cycle count.

Measured: a blocked GEMM has zero read conflicts (A, B and C are in three
different banks by construction), while an encoder layer lost 12% of all
cycles to them. Most of that was one pattern — a two-source VEC op whose B
operand is literally the same stream as A, as in the LayerNorm variance
term `x*x`, making both read ports hit the same bank every cycle. VEC now
detects that case and reuses the A beat instead of issuing a second read,
which took the layer to 9%. What remains is cross-pipe contention, which is
the compiler's allocation to fix rather than the hardware's.

## 11. Debug build options

Two guarded trace levels, both compiled out by default:

| Define | Effect |
|---|---|
| `NPU_DEBUG` | on `err_hang`, dumps the issue window (pipe, queue, opcode, tag, wait mask, barrier flags), the event vector, the in-flight total, the fetch-path state and every pipe credit |
| `NPU_TRACE` | one line per issue, per discarded illegal op and per window fetch |

The `err_hang` dump is the one that pays for itself: it is what turned a
cross-core deadlock from "the machine stopped" into "the scheduler is
holding a barrier whose producer is stuck behind it in the window".

Two build parameters are overridable for experiments:
`-DNPU_MAX_BURST=<n>` and `-DNPU_AXI_IDW=<n>`, plus `-DMEM_LAT=<n>` for the
testbench memory model. `scripts/sweep_mem.sh` uses all three.
