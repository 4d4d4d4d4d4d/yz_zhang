# Instruction set specification

A task is a 256-bit descriptor pushed into a message queue. There is no
instruction fetch from memory: the MCUs write descriptors, the hardware
schedules them.

## 1. Descriptor envelope

| Bits | Field |
|---|---|
| 255:64 | pipe-specific payload (192 bit) |
| 63:48 | reserved, must be zero |
| 47:32 | `wait_mask` — one bit per event |
| 31:0 | header |

### Header, bits 31:0

| Bits | Field | Meaning |
|---|---|---|
| 0 | `vld` | must be 1; 0 raises `err_illegal` and the op is discarded |
| 3:1 | `pipe` | 0 CUBE, 1 VEC, 2 FIX, 3 MTE_IN, 4 MTE_OUT |
| 9:4 | `opc` | pipe-specific; `0x3F` is the universal NOP |
| 17:10 | `tag` | software-supplied, echoed in the completion and in `ERR_TAG` |
| 18 | `set_en` | set one event on completion |
| 22:19 | `set_evt` | which event |
| 23 | `bar_q` | queue-scope barrier |
| 24 | `bar_g` | global barrier |
| 25 | `fp` | 0 = int16 fixed, 1 = bf16 float |
| 31:26 | reserved |

`qid` and `mcu_id` are **not** in the descriptor. Hardware fills them from
the queue the descriptor lands in and the ingress port it arrived on, so
software cannot forge them. That is what makes the completion route
trustworthy and the `LOCK` owner field meaningful.

## 2. Synchronisation

`wait_mask` is a bitmap; the op issues only when every selected event has a
non-zero count, and issuing decrements each of them by one.

**A descriptor may set at most one event.** Waking N consumers therefore
costs N−1 trailing no-ops on the producer's own pipe and queue, where
hardware ordering guarantees they retire after it. This is a real ISA
limit. Widening `set_evt` into a bitmap would remove it at the cost of 12
more descriptor bits and a wider increment port on the semaphore file; it
is the first thing to change if the sync no-op count ever becomes
significant (it is 16 of 189 descriptors in the encoder layer, about 8%).

Event counters are 3 bits and **saturate**. More than 7 pending sets are
swallowed and the matching waits then hang forever. That is unavoidable for
a finite counter; what is not acceptable is that it hangs silently, so
saturation raises the sticky `STATUS.err_evt_ovf`.

## 3. CUBE

`opc = 0` (`C_MM`). `C[i][j] += A[k][i] · B[k][j]`, `k = 0 .. k_len-1`.

| Bits | Field | Meaning |
|---|---|---|
| 15:0 | `src_a` | A base, on-chip |
| 31:16 | `src_b` | B base |
| 47:32 | `dst` | C base |
| 67:64 | `rows` | rows − 1 |
| 71:68 | `n_dim` | cols − 1 |
| 72 | `acc_cont` | do not clear the accumulator on entry |
| 73 | `acc_hold` | do not write back; keep the accumulator |
| 74 | `relu` | clamp negative results to zero on writeback |
| 79:75 | `shift` | fixed point: `acc >> shift`, round half away from zero, saturate |
| 95:80 | `k_len` | reduction length, ≥ 1 |
| 111:96 | `a_stride` | beats between successive k of A |
| 127:112 | `b_stride` | beats between successive k of B |
| 143:128 | `c_stride` | beats between successive rows of C |

Writeback converts the 32-bit accumulator to 16 bits: `shift_sat` in fixed
point, round-to-nearest-even to bf16 in float. Only lanes `0 .. n_dim` are
written; the rest of the destination beat is untouched.

`acc_hold` on one descriptor and `acc_cont` on the next relay a partial sum
through the accumulator, so a reduction longer than a buffer never has to
spill. The accumulator is machine state: an `acc_cont` descriptor sees
whatever the previous CUBE op left, so the compiler owns that lifetime.

## 4. VEC

| Bits | Field |
|---|---|
| 15:0 | `src_a` |
| 31:16 | `src_b` |
| 47:32 | `dst` |
| 63:48 | `rows` (beats processed, ≥ 1) |
| 79:64 | `mask` — static lane predicate, applied to every write |
| 95:80 | `a_stride` |
| 111:96 | `b_stride` |
| 127:112 | `d_stride` |
| 159:128 | `imm` |
| 161:160 | `subop` — 0 add, 1 sub, 2 mul, 3 max (for `BRC_*`) |

`imm[15:0]` is the immediate operand (int16 or bf16), `imm[20:16]` a shift
used by fixed-point multiply, reductions and conversions, and
`imm[25:21]` the slope shift for `V_LUT`.

| `opc` | Name | Semantics |
|---|---|---|
| 0 | `V_MOV` | `dst = a` |
| 1..3 | `V_ADDI` `V_MULI` `V_MAXI` | `a` against `imm[15:0]` |
| 4..8 | `V_ADD` `V_SUB` `V_MUL` `V_MAX` `V_MIN` | two-source tensor |
| 9 | `V_BRC_R` | `dst[r][l] = a[r][l] ⊕ b[0][l]` — a row vector held for every row |
| 10 | `V_BRC_C` | `dst[r][l] = a[r][l] ⊕ b[r/16][r mod 16]` — one scalar per row |
| 11,12 | `V_RED_SUM` `V_RED_MAX` | reduce across lanes; one scalar per row, packed 16 per beat |
| 13 | `V_LUT` | 16-segment piecewise linear; `src_b` holds slopes then intercepts |
| 14 | `V_RECIP` | reciprocal; **bf16 only**, a fixed-point descriptor is a configuration error |
| 15 | `V_SEL` | `dst = a` under `mask` only |
| 16 | `V_SELD` | `dst = a` where `mask` and `b > 0` |
| 17,18 | `V_CVT_F2I` `V_CVT_I2F` | bf16 ↔ int16 with `imm[20:16]` as the binary point |

`V_LUT` segment index: `clamp((a − imm[15:0]) >> imm[20:16], 0, 15)` in
fixed point, or the same computed through fp32 in float. The result is
`slope[i]·a + intercept[i]`.

Every VEC write is predicated by `mask`, and `V_SELD` further predicates
per lane on the sign of B. Lane-granular writes are exactly why the ECC
code word is 16 bits wide.

## 5. FIX

`opc = 0` (`F_TRANS`). Transposes `tiles` consecutive 16×16 tiles.

| Bits | Field |
|---|---|
| 15:0 | `src_a` |
| 31:16 | `s_stride` — beats between input tiles |
| 47:32 | `dst` |
| 63:48 | `tiles` ≥ 1 |
| 79:64 | `d_stride` — beats between output tiles |

## 6. MTE_IN / MTE_OUT

`opc = 0` (`M_XFER`). A 2-D window with an optional intra-row stride.

| Bits | Field |
|---|---|
| 47:0 | `ext_addr` — byte address, beat aligned. Bits 47:32 are reserved for a future MMU and must be zero |
| 63:48 | `buf_addr` |
| 79:64 | `buf_rstride` |
| 95:80 | `cols` — beats per row, ≥ 1 |
| 111:96 | `rows` ≥ 1 |
| 143:112 | `ext_rstride` — beats |
| 159:144 | `in_cnt` — beats per intra-row group; 0 means contiguous |
| 175:160 | `in_stride` — beats between groups |

For row `r`, column `c`, with `g = c / in_cnt` and `w = c mod in_cnt`:

```
external beat = ext_addr/32 + r·ext_rstride + g·in_stride + w
on-chip beat  = buf_addr    + r·buf_rstride + c
```

The intra-row stride is what turns a strided gather into one descriptor
instead of a rearrangement pass. `cols` must be a multiple of `in_cnt`.

## 7. Configuration errors

Each pipe validates its descriptor and reports `err` in its completion,
which raises the sticky `STATUS.err_task` and latches `{tag, mcu, pipe}`
into `ERR_TAG`. The op does not execute.

- `opc` is not defined for the pipe
- a zero length (`k_len`, `rows`, `cols`, `tiles`)
- an operand window leaves its buffer: `base + (n−1)·stride ≥ 256`
- `V_RECIP` with `fp = 0`
- `cols` not a multiple of `in_cnt`
- `ext_addr` not beat aligned

**A single operand may not cross a buffer boundary.** The hardware checks
it and reports rather than wrapping, which turns an allocator bug into a
named error instead of a silently wrong result.

A NOP (`opc = 0x3F`) is legal on every pipe, does nothing, and still sets
its event — it is the mechanism for fanning one producer out to several
consumers, and it must not be confused with an error.
