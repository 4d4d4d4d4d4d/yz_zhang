# Control plane specification

Control is a separate bus from data: AXI4-Lite slave, single cycle, no
burst, no ID reordering. A configuration read must not queue behind a
16-beat burst of activations.

## 1. Register map

| Offset | Name | Access | Contents |
|---|---|---|---|
| `0x00` | `MAGIC` | RO | `0x4E505501` — identity and version |
| `0x04` | `STATUS` | RO | `{ [4] idle, [3] err_hang, [2] err_task, [1] err_evt_ovf, [0] err_illegal }` |
| `0x08` | `ISSUED` | RO | ops issued since the last clear |
| `0x0C` | `CYCLE` | RO | cycles since the last clear |
| `0x10` | `WIN_FULL` | RO | cycles the issue window was full — *is the window deep enough* |
| `0x14` | `MQ_FULL` | RO | cycles a push was blocked — *is software keeping up* |
| `0x18` | `EXT_RD` | RO | cycles with a read outstanding — *is the bandwidth used* |
| `0x1C` | `EXT_WR` | RO | cycles with a write outstanding |
| `0x20` | `ERR_TAG` | RO | `{tag[12:5], mcu[4:3], pipe[2:0]}` of the first failing op |
| `0x24` | `HANG_SNAP` | RO | per-pipe in-flight count at the moment the watchdog fired, 4 bits each |
| `0x40 + 4i` | `BUSY[i]` | RO | busy cycles of pipe *i* — *which pipe is the bottleneck* |
| `0x80` | `CTRL` | WO | bit 0 clears all counters, error flags and event counters |
| `0x84` | `QPRIO` | RW | high-priority queue bitmap |
| `0x88` | `ECCINJ` | RW | `{ [5:4] bank, [1:0] mode }` — 01 one bit, 10 two bits |
| `0x8C` | `ECC_CE` | RO | corrected single-bit errors |
| `0x90` | `ECC_UE` | RO | uncorrectable double-bit errors |
| `0x94` | `ECC_FIRST` | RO | `{buffer[9:8], beat[7:0]}` of the first error |
| `0x100 + 4i` | `LOCK[i]` | R/W | hardware semaphore, read to acquire |

Writes are whole-word: a partial byte strobe is accepted on the bus and
changes nothing, rather than half-updating a control field.

The counters are not decoration. "MAC utilisation 59%, MTE_IN busy 96% of
all cycles" is read straight out of `BUSY[i]`, `CYCLE` and `EXT_RD`.
Without them the only available answer is a guess.

## 2. Task submission

Four MCU ports feed eight queues of sixteen entries. One push and one pop
per cycle, so the queue array maps to a single SRAM macro. A full queue
back-pressures; nothing is dropped or overwritten.

`qid` comes from the queue the descriptor physically lands in and `mcu_id`
from the ingress port index, neither from the descriptor.

Pop uses two priority levels: any non-empty high-priority queue wins, with
round-robin inside each level so neither level starves internally. The
bitmap is `QPRIO`.

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
| `err_hang` | no issue and no completion for 4096 cycles with work outstanding | carries a per-pipe in-flight snapshot |

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
