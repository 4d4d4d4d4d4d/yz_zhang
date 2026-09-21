"""Layout bookkeeping -- the part of an NPU compiler that actually costs.

CUBE computes C[i][j] = sum_k A[k][i] * B[k][j] and reads one beat of each
operand per cycle, so both operands must be contiguous along k. Writing
Y = X.W that way means:

    A operand = beats indexed by k, lanes = output row  -> X held as X^T
    B operand = beats indexed by k, lanes = output col  -> W as-is
    result    = beats indexed by row, lanes = col       -> Y in row order

So every matrix multiply CONSUMES its left operand transposed and PRODUCES
its result untransposed. Chain two of them and the layouts do not meet. A
row reduction has the opposite preference: VEC reduces across lanes, so it
wants the reduced axis in the lanes, i.e. row order.

That conflict is not avoidable by being clever with addresses; the compiler
has to track which orientation each tensor is in and insert a transpose at
the boundary. These two helpers are the whole of that bookkeeping.

    ROW(Z)  beat(r, cj) = base + cj*R + r     R rows contiguous per col tile
    SEG(Z)  = ROW(Z^T)                        K rows contiguous per row tile
"""
from npu_isa import LANES


def row_beat(base, rows, r, cj):
    """Address of row r inside column tile cj of a ROW-layout tensor."""
    return base + cj * rows + r


def seg_beat(base, k_rows, kk, rj):
    """Address of reduction row kk inside row tile rj of a SEG tensor."""
    return base + rj * k_rows + kk


def row_size(rows, cols):
    return ((cols + LANES - 1) // LANES) * rows


def seg_size(rows, cols):
    return row_size(cols, rows)


def tile_pairs(rows, cols):
    """(row tile, col tile) pairs covering a tensor."""
    for ri in range((rows + LANES - 1) // LANES):
        for ci in range((cols + LANES - 1) // LANES):
            yield ri, ci


def transpose_plan(row_base, seg_base, rows, cols):
    """FIX descriptors turning ROW(Z) into SEG(Z) = ROW(Z^T).

    Tile (ri, ci) of ROW(Z) sits at row_base + ci*rows + ri*16 and belongs at
    seg_base + ri*cols + ci*16 once transposed. The mapping is not a constant
    stride across tiles, so this costs one descriptor per 16x16 tile. That is
    the price of the boundary, and it is why the layout assignment is worth
    getting right rather than transposing everywhere.
    """
    out = []
    for ri, ci in tile_pairs(rows, cols):
        out.append((row_base + ci * rows + ri * LANES,
                    seg_base + ri * cols + ci * LANES))
    return out
