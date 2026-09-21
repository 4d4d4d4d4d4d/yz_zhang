# Numeric specification

Two data types share the 16-bit lane. Everything below is what the RTL
does, checked against IEEE doubles in `tb/tb_fp.sv` (14000 assertions).

## 1. Fixed point

`int16 × int16 → int32`, exact. The accumulator is int32 throughout; K is
unbounded because nothing is rounded until writeback.

Writeback applies `shift_sat`: arithmetic right shift by `shift`, rounding
**half away from zero**, then saturation to int16. Saturation is silent —
there is no overflow flag, so the binary point is the compiler's problem.

VEC add and subtract saturate. VEC multiply is `(a·b) >> imm[20:16]` with
the same rounding and saturation.

## 2. bf16

Sign, 8 exponent bits, 7 mantissa bits — the top half of a binary32. The
declared semantics are narrower than IEEE-754 on purpose, and the narrowing
is part of the contract:

- **Subnormals are flushed to zero**, on input and on every result.
- **Round to nearest, ties to even** is the only rounding mode. There is no
  rounding-mode control.
- **NaN carries no payload.** Any NaN result is the canonical quiet NaN
  (`0x7FC0`, or `0x7FC00000` in fp32). Nothing is propagated.

### 2.1 Multiply is exact

`bf16 × bf16 → fp32` never rounds. An 8×8-bit significand product is 16
bits and fp32 carries 24, so the multiplier is exact by construction and
all the rounding in a matrix multiply happens in the accumulator and once
more at writeback. This is the reason a long K reduction in bf16 stays
close to a float64 reference: with K = 256 the measured error is under
1e-5 relative.

### 2.2 Accumulation

CUBE accumulates in fp32 with round-to-nearest-even per addition.
Writeback rounds once more to bf16.

### 2.3 Reciprocal

Exponent negation is exact. The mantissa uses a Q16 Newton-Raphson
iteration seeded by the classic minimax line `r0 = 48/17 − 32/17·m'` with
`m' = m/2 ∈ [0.5, 1)`. Three steps take the initial 6% error below one ulp
of Q16, well inside what an 8-bit significand can represent. Measured worst
case over 2000 random inputs: **0.35%**, against the 0.5% the test allows.

`1/0` is `±inf`, `1/inf` is `±0`, `1/NaN` is the canonical quiet NaN.
`V_RECIP` is defined for bf16 only; a fixed-point descriptor raises
`err_task`.

### 2.4 Conversion

`bf16 → int` truncates toward zero. Infinity saturates to the signed
extreme; **NaN converts to zero**, because it carries no payload and
saturating it would look like a legitimate large value.

`int → bf16` rounds to nearest even.

## 3. Transcendentals

There are none in hardware. `exp`, `GELU` and `sqrt` are 16-segment
piecewise linear tables evaluated by `V_LUT`, fitted by the compiler over
a range it chooses. The table is two beats of on-chip data — slopes then
intercepts — so a kernel can carry several and switch per op.

Measured on a full encoder layer (`tools/gen_encoder.py`, S=32, d=32,
d_ff=64) against a float64 reference:

| Stage | Relative error |
|---|---|
| Q = X·Wq | 0.31% |
| scores·scale | 0.34% |
| ctx = P·V | 1.85% |
| attn·Wo | 1.90% |
| LayerNorm 1 | 1.20% |
| GELU(N1·W1) | 1.33% |
| H·W2 | 2.05% |
| LayerNorm 2 | 1.64% |

The table's **range** matters more than its existence. Covering `sqrt` over
`[0,4)` in 16 segments left LayerNorm at 6.6%, because all of the curvature
is near zero and one segment was doing the work of five. Narrowing to
`[0,2)` — the range the variance actually occupies after centering — took
the same table to 1.20%, and every stage downstream followed. Fitting a
table is cheap; choosing where to put it is the part that needs measuring.

## 4. fp16

Not supported, and not recommended. bf16 has the same exponent range as
fp32, so a conversion never overflows and no loss scaling is needed. fp16
buys three mantissa bits in exchange for a narrower exponent range,
gradual-underflow handling and a second conversion path through every
unit. For this workload the three bits are not where the error is — the
table above shows the piecewise-linear approximations dominating by an
order of magnitude.
