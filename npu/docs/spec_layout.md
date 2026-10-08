# Layout specification

The single largest source of complexity in a compiler for this machine is
not scheduling. Scheduling is regular and reusable; layout has to be
recomputed for every network and every shape, and it can generate more work
than the computation it is serving.

## 1. The conflict

CUBE computes

```
C[i][j] = Σ_k A[k][i] · B[k][j]
```

and reads one beat of each operand per cycle, so both must be contiguous
along k. Writing `Y = X·W` that way means:

| Operand | Indexed by | Lanes | So the matrix must be |
|---|---|---|---|
| A | k | output row | `X` transposed |
| B | k | output col | `W` as-is |
| result | output row | output col | `Y` not transposed |

**Every matrix multiply consumes its left operand transposed and produces
its result untransposed.** Chain two of them and the orientations do not
meet.

A VEC row reduction has the opposite preference: it reduces across lanes,
so it wants the reduced axis in the lanes — row order, not transposed.
Softmax and LayerNorm both live there.

No addressing trick reconciles these. The compiler has to track which
orientation each tensor is in and insert a transpose where it flips.

## 2. The two layouts

```
ROW(Z)  beat(r, cj) = base + cj·R + r      R rows contiguous per column tile
SEG(Z)  = ROW(Zᵀ)                          K rows contiguous per row tile
```

`tools/npu_layout.py` is the whole of the bookkeeping: address arithmetic
for both, and `transpose_plan()`, which emits the FIX descriptors that turn
one into the other. Tile `(ri, ci)` of `ROW(Z)` sits at `base + ci·R +
ri·16` and belongs at `seg + ri·C + ci·16` once transposed. That mapping is
not a constant stride across tiles, so it costs one descriptor per 16×16
tile — the price of the boundary, and the reason the assignment is worth
getting right rather than transposing everywhere.

## 3. What it costs in practice

A full encoder layer (S=32, d=32, d_ff=64) is 189 descriptors, of which
**32 (17%) are transposes**. Every one sits at a boundary the layout
assignment could not remove:

| Boundary | Why |
|---|---|
| X → SEG(X) | Q, K and V all need X transposed |
| Q → SEG(Q), K → SEG(K) | `scores = Q·Kᵀ` needs **both** operands transposed |
| P → SEG(P) | `ctx = P·V` after softmax produced P in row order |
| ctx → SEG(ctx) | output projection |
| N1 → SEG(N1) | feed-forward layer 1, after LayerNorm produced row order |
| H → SEG(H) | feed-forward layer 2, after GELU |

The softmax and LayerNorm boundaries are the expensive ones and they are
structural: a reduction must produce row order and the next multiply must
consume transposed order.

## 4. Addressing instead of rearranging

The MTE intra-row stride (`in_cnt` / `in_stride`) covers the cases where
the data is already where it needs to be but strided. A gather that would
otherwise be a separate rearrangement pass becomes one descriptor and one
burst chain. This is the difference between a layout boundary that costs a
transpose and one that costs nothing.

## 5. Layout is also bandwidth

The reduction axis has to be contiguous in **external** memory too, or the
AGU emits one burst per beat. In `tools/gen_gemm.py`, moving A, B and C
from row-major to tile-major (SEG) order — same data, same descriptors,
different address arithmetic — took a 32×32×64 GEMM from 3918 cycles to
1198. Nothing else changed.

The second lever is residency. A 16×16 tile has an arithmetic intensity of
8 against a hardware balance point of 16, so on paper it is a factor of two
short of feeding the array. Holding one operand resident across the inner
sweep brings traffic to `(1 + 1/nt)` beats per MAC cycle, which is 1.06 at
`nt = 16`. Adding MAC units would not have helped; the next real step would
be more accumulators.
