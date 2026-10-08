# Control plane specification

Control is a separate bus from data: AXI4-Lite slave, single cycle, no
burst, no ID reordering. A configuration read must not queue behind a
16-beat burst of activations.

## 1. Register map

| Offset | Name | Access | Contents |
|---|---|---|---|
| `0x00` | `MAGIC` | RO | `0x4E505503` — identity and version |
| `0x04` | `STATUS` | RO | `{ [4] idle, [3] err_hang, [2] err_task, [1] err_evt_ovf, [0] err_illegal }` |
| `0x08` | `ISSUED` | RO | ops issued since the last clear |
| `0x0C` | `CYCLE` | RO | cycles since the last clear |
| `0x10` | `WIN_FULL` | RO | cycles the issue window was full — *is the window deep enough* |
| `0x14` | `MQ_FULL` | RO | cycles a push was blocked — *is software keeping up* |
| `0x18` | `EXT_RD` | RO | cycles with a read outstanding — *is the bandwidth used* |
| `0x1C` | `EXT_WR` | RO | cycles with a write outstanding |
| `0x20` | `ERR_TAG` | RO | `{tag[12:5], mcu[4:3], pipe[2:0]}` of the first failing op |
| `0x24` | `HANG_SNAP` | RO | per-pipe in-flight count at the moment the watchdog fired, 4 bits each |
| `0x28` | `IRQ_STATUS` | RW1C | sticky interrupt sources, see below |
| `0x2C` | `IRQ_ENABLE` | RW | mask; `irq = \|(IRQ_STATUS & IRQ_ENABLE)` |
| `0x30` | `CONFIG0` | RO | `{MAX_BURST[31:24], NID[23:16], CREDIT[15:8], WIN[7:0]}` |
| `0x34` | `CONFIG1` | RO | `{NBUF[31:24], NQ[23:16], NPIPE[15:8], NEVT[7:0]}` |
| `0x38` | `CONFIG2` | RO | `{BUF_D[31:16], LANES[15:8], EVT_W[7:0]}` |
| `0x3C` | `CONFIG3` | RO | `{NRGN[31:24], PG_SH[23:16], VA_W[15:8], AXI_AW[7:0]}` |
| `0x40 + 4i` | `BUSY[i]` | RO | busy cycles of pipe *i* — *which pipe is the bottleneck* |
| `0x80` | `CTRL` | WO | bit 0 clears all counters, error flags and event counters |
| `0x84` | `QPRIO` | RW | high-priority queue bitmap |
| `0x88` | `ECCINJ` | RW | `{ [5:4] bank, [1:0] mode }` — 01 one bit, 10 two bits |
| `0x8C` | `ECC_CE` | RO | corrected single-bit errors |
| `0x90` | `ECC_UE` | RO | uncorrectable double-bit errors |
| `0x94` | `ECC_FIRST` | RO | `{buffer[9:8], beat[7:0]}` of the first error |
| `0x98` | `SOFT_RST` | RW | one bit per pipe; write 1 to reset, reads 0 when done |
| `0x9C` | `XBAR_RCONF` | RO | cycles a read requester asked and was refused |
| `0xA0` | `XBAR_WCONF` | RO | cycles a write requester asked and was refused |
| `0xA4` | `STALL_DEP` | RO | cycles the oldest op was waiting on an event |
| `0xA8` | `STALL_CRED` | RO | cycles it was waiting on an issue credit |
| `0xAC` | `STALL_ORD` | RO | cycles it was waiting on `(pipe, queue)` order |
| `0x100 + 4i` | `LOCK[i]` | R/W | hardware semaphore, read to acquire |
| `0x200 + 16i + 0` | `MMU_VA[i]` | RW | `vpn[27:0]` — virtual page number of region *i* |
| `0x200 + 16i + 4` | `MMU_PA[i]` | RW | `ppn[19:0]` — physical page it maps to |
| `0x200 + 16i + 8` | `MMU_ATTR[i]` | RW | `{ [18:3] pages, [2] write, [1] read, [0] valid }` |
| `0x280` | `MMU_CTRL` | RW | bit 0 enables translation; 0 is identity |
| `0x284` | `MMU_FAULT` | RW1C | `{ [3] port (0 = MTE_IN), [2:1] kind, [0] valid }` |
| `0x288` | `MMU_FVA_LO` | RO | faulting virtual address, bits `[31:0]` |
| `0x28C` | `MMU_FVA_HI` | RO | faulting virtual address, bits `[39:32]` |

The address space is three pages: `0x000` the main block, `0x100` the
hardware semaphores, `0x200` the region table. Each page decodes only its
own range — an undecoded offset reads zero and a write to it changes
nothing. Before the region table existed every page above the semaphores
aliased onto the main block, so a read of `0x384` returned `QPRIO`.

Writes are whole-word: a partial byte strobe is accepted on the bus and
changes nothing, rather than half-updating a control field.

The counters are not decoration. "MAC utilisation 59%, MTE_IN busy 96% of
all cycles" is read straight out of `BUSY[i]`, `CYCLE` and `EXT_RD`.
Without them the only available answer is a guess.

## 1.1 Address translation

Eight regions, each a run of 4 KiB pages mapped contiguously, programmed
by software. There is no hardware page-table walker, on purpose; see
`spec_arch.md` section 8 for the argument.

A region matches when `vpn - MMU_VA[i]` is below `MMU_ATTR[i].pages` and
the entry is valid. Overlapping regions resolve to the **lowest** matching
index, which makes a one-page region at index 0 an override of a large one
at a higher index — that is how a driver pins one tensor somewhere else
without rebuilding the table. A valid entry with `pages = 0` covers
nothing.

`read` and `write` are checked against the engine asking: MTE_IN is the
read port, MTE_OUT the write port. A read-only region therefore protects a
weight tensor from a mis-encoded MTE_OUT, which is otherwise a silent
corruption discovered only when the numbers come out wrong.

With `MMU_CTRL.en = 0` translation is identity — but not unchecked. A
virtual address above the 32-bit physical window still faults instead of
being truncated, which is what the pre-translation design did.

A fault aborts the transfer and is reported through the ordinary error
path: `cpl.err` → `STATUS.err_task` → `ERR_TAG` → `IRQ_STATUS[4]`, with
`SOFT_RST` as the recovery. `MMU_FAULT` adds what that path cannot carry:
which engine, whether the address was unmapped or merely not permitted,
and the address itself. The first fault is kept, because the address that
started the failure is more useful than the last of the cascade behind it.
Acknowledging a fault whose cause is still live takes, and the next cycle
that still presents the address reports it again — clearing the register
without fixing the mapping cannot leave an engine running on a translation
nobody was told about. `CTRL` bit 0 also drops the capture, for the same
reason it drops `ECC_FIRST`: leaving a stale fault address behind after
`STATUS.err_task` has been cleared is worse than no address at all.

The region table itself is control-plane state owned by software, so it
survives `SOFT_RST` of either memory engine and is cleared only by a full
reset.

Note the distinction from a configuration error. `ext_addr` above the
40-bit virtual space is rejected at descriptor decode, before any
translation is attempted, and reports no VA — there is no virtual address
to report. A window that *starts* inside a region and runs off its end is
the opposite case: it faults part way through, after bursts have already
gone out, which is exactly what a bounds check on the descriptor could not
have caught.

## 2. Task submission

Four MCU ports feed eight queues of sixteen entries. One push and one pop
per cycle, so the queue array maps to a single SRAM macro. A full queue
back-pressures; nothing is dropped or overwritten.

`qid` comes from the queue the descriptor physically lands in and `mcu_id`
from the ingress port index, neither from the descriptor.

Pop uses two priority levels: any non-empty high-priority queue wins, with
round-robin inside each level so neither level starves internally. The
bitmap is `QPRIO`.

## 2.1 Interrupts

| Bit | Source |
|---|---|
| 0 | `IRQ_DONE` — an op completed |
| 1 | `IRQ_IDLE` — the machine went idle (rising edge) |
| 2..5 | `err_illegal`, `err_evt_ovf`, `err_task`, `err_hang` |
| 6,7 | corrected and uncorrectable ECC errors |

All sources are sticky and cleared by writing a one. `IRQ_IDLE` is the
edge, not the level: it is what a submitting core actually waits for, and
it is what removes the `STATUS` polling loop. Masking a source with
`IRQ_ENABLE` hides it from the line but does not stop it being recorded, so
software can enable one source, sleep, and then read the full picture.

## 2.2 Per-pipe soft reset

`SOFT_RST` takes one bit per pipe. Writing a one holds that unit's reset
for a few cycles; the bit reads back zero once the unit is up and the
scheduler has taken back what the abandoned ops were holding:

- every issue credit for that pipe
- the in-flight accounting, which is tracked per (pipe, queue) precisely so
  a reset can give back exactly what one pipe owed — the queue-scope
  barrier reads `ifq` and would deadlock on a stale count
- the sticky `err_hang`, since the machine has demonstrably recovered

While a reset is active the scheduler issues nothing to that pipe and
ignores any completion it emits.

**What a soft reset costs.** CUBE loses its accumulator, so a partial sum
being relayed across descriptors does not survive. Any AXI transaction the
unit had outstanding is abandoned: the interconnect still owes responses
for it, and those responses will arrive after the unit has forgotten them.
Two things follow, and both are implemented:

1. The AXI ID ownership tracker lives **outside** the unit's reset domain.
   An ID whose response is still owed cannot be re-allocated, or a late
   beat from the abandoned burst would be counted against the new transfer.
2. A beat arriving for an ID this transfer does not own is accepted (so the
   bus does not stall) and discarded (so it does not land in a buffer) —
   and it does **not** return an outstanding credit, because it never
   reserved one. Letting it do so underflows the credit counter, which then
   reads as "no room" forever and hangs the very pipe the reset was
   supposed to recover.

## 2.3 Event recycling: a contract, not a convention

A counting semaphore carries no identity. A consumer that finds its event
non-zero cannot tell whose set it is taking, so reusing an event for a new
producer while an old consumer might still be waiting lets the new
consumer steal the old set. That is a hang, and it is what
`STATUS.err_hang` exists to report.

Two cheaper rules were tried against this and both are unsound. They are
recorded because both look correct:

1. *"At least WIN ops apart, on a single queue."* This assumed the issue
   window spans a bounded stretch of program order. It does not — the
   window holds the oldest un-issued op plus later fetched ops, and as the
   ops between them retire fetching continues, so the span has no bound.
2. *"A happens-before path from every old consumer to the new producer."*
   Circular: the only thing ordering a new consumer is its own wait on this
   event, so the path runs through the very edge being aliased.

The sound rule is a global barrier between the old consumer and the new
producer, because passing one requires the machine to be drained. It is
expensive, which is why the event file is 32 wide rather than 16 — the
answer to running out of events is more events.

`CONFIG` reports what the compiler bakes into what it emits:

| Offset | 31:24 | 23:16 | 15:8 | 7:0 |
|---|---|---|---|---|
| `0x30` | `MAX_BURST` | `NID` | `CREDIT` | `WIN` |
| `0x34` | `NBUF` | `NQ` | `NPIPE` | `NEVT` |
| `0x38` | `BUF_D` (31:16) | | `LANES` | `EVT_W` |
| `0x3C` | `NRGN` | `PG_SH` | `VA_W` | `AXI_AW` |

A program records what it assumed and the testbench checks it; a window
deeper than the one a program targeted is a named failure rather than a
hang. `CONFIG3` is there for the same reason: a driver that lays out eight
regions on a device with fewer, or assumes 4 KiB pages on one built with
larger, should find out by reading a register rather than by producing
wrong addresses.

## 2.4 Stall attribution

`WIN_FULL` alone cannot distinguish "the window is too shallow" from "the
dependency graph is serial", and those want opposite fixes. `STALL_DEP`
(0xA4), `STALL_CRED` (0xA8) and `STALL_ORD` (0xAC) count stalled cycles
attributed to the oldest un-issued op, which is the one gating progress.

Measured, and it settles the question: an encoder layer spends 85% of its
cycles stalled on a dependency and 0% on ordering, and making the window
16 or 32 deep does not help — it is slightly *worse*, because a deeper
window makes the compiler's event live ranges longer and buys barriers
rather than overlap.

## 3. Completion

Every pipe returns `{tag, mcu_id, qid, set_evt, set_en, err}`. The
completion drives three things: the event set, the issue-credit return, and
the error path. `err` is raised only for a configuration error — a
zero-length op is a legitimate NOP that the compiler relies on for event
fan-out, and conflating the two would make the error flag useless.

## 4. RAS

Four sticky error bits, each for a different failure class:

| Bit | Meaning | Why it is separate |
|---|---|---|
| `err_illegal` | undefined pipe encoding | the op is discarded and the pipeline keeps running |
| `err_evt_ovf` | an event counter saturated | turns "software set/wait is unbalanced" from a silent hang into something locatable |
| `err_task` | descriptor configuration error | carries `{tag, mcu, pipe}`, so it points at one descriptor |
| `err_hang` | no issue and no completion for 4096 cycles with work outstanding | carries a per-pipe in-flight snapshot; recoverable with a per-pipe soft reset |

The snapshot is what makes `err_hang` useful. A cross-core deadlock in this
design showed up as `err_hang = 1` with `HANG_SNAP = 0x00000` — every pipe
idle and the machine still not moving — which points at the scheduler, not
at an execution unit. A stuck unit would have shown a non-zero count.

Alongside these: ECC CE/UE counters with the first error's location, RTL
handshake checkers (`npu_check`: valid may not be withdrawn before ready,
payload may not change while valid is held) and a credit assertion in
`npu_top`.

## 5. Multi-core

Eight hardware semaphores, **read to acquire**. Acquisition has to complete
inside one bus transaction, or two cores both observe "free"; for cores with
no atomic instruction this is the only mutual exclusion primitive
available. A read returns `{ [16] held, [9:8] owner, [0] you now own it }`
and grants the lock in the same transaction that reported it free. The
owner is taken from `ARID`, which the interconnect drives, so a non-owner
writing the register does not release it.

## 6. Low power (Q-Channel)

Four-wire `qreqn` / `qacceptn` / `qdeny` / `qactive`. The only interesting
part is what counts as quiescent:

```
quiescent = scheduler idle and the fetch path empty
          && no AXI read transaction outstanding   (AR sent, R not back)
          && no AXI write transaction outstanding  (AW sent, B not back)
```

Drop either of the last two and power goes away with transactions in
flight: they never return, the bus hangs, and nothing on chip can say why.

A descriptor parked in the skid buffer is in neither the message queue nor
the issue window, so "fetch path empty" has to include it. The same term is
needed for `STATUS.idle` — without it software reads "done" for the cycle
or two the hand-over takes and then reads a result that was never produced.

`q_stop` gates instruction fetch, and it gates **both** sides of that
handshake. Masking valid alone loses a descriptor the consumer has already
accepted; masking ready alone lets the producer re-present one that was
already taken.
