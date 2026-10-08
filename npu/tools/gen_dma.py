#!/usr/bin/env python3
"""Exercise the 2-D strided AGU, in both directions.

Coverage said this was the biggest hole: no generated program had ever used
rows > 1 or a non-zero intra-row stride, and the intra-row stride is the
feature that turns a strided gather into one descriptor instead of a
rearrangement pass. The RTL AGU and the model's agu() have to walk the same
window in the same order, and nothing was checking that.

Each case loads a window with one shape and stores it back with another, so
a disagreement about addressing shows up as misplaced beats rather than as
a hang.
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import npu_isa as I
import npu_sched
import npu_model as M
from npu_sched import Builder, beats, ext_beats

# (rows, cols, in_cnt, in_stride, ext_rstride) -- in_cnt 0 means contiguous
CASES = [
    (1,  4,  0, 0,  4),      # the shape every other generator uses
    (4,  4,  0, 0,  4),      # multi-row, contiguous rows
    (4,  4,  0, 0,  9),      # multi-row with a gap between rows
    (3,  8,  4, 16, 64),     # intra-row stride: two groups of 4, 16 apart
    (2,  6,  2, 5,  32),     # groups of 2 at stride 5
    (1,  20, 0, 0,  20),     # longer than MAX_BURST, so the burst caps
    (2,  18, 6, 8,  40),     # both: capped bursts and grouped addressing
    (5,  1,  0, 0,  3),      # one beat per row, five single-beat bursts
]


def agu_window(cfg):
    """The external beats a descriptor touches, in walk order."""
    return [e for e, _b in M.agu(cfg)]


def gen(seed):
    rng = random.Random(seed)
    mach = M.Machine()
    prog = I.Program()
    b = Builder(single_queue=True, verbose=False)

    # fill a generous source area with distinguishable data
    SRC = 0
    for i in range(512):
        mach.mem_set(SRC + i, [M.sat16((i * 16 + l) % 30000)
                               for l in range(I.LANES)])
    for beat in sorted(mach.mem):
        prog.mem(beat, mach.mem_word(beat))

    DST = 1024
    buf = 0
    checks = []
    for ci, (rows, cols, in_cnt, in_stride, ext_rs) in enumerate(CASES):
        # on-chip landing area, one buffer per case so cases do not alias
        bufid = ci % I.NBUF
        base = I.addr(bufid, 0)
        n_beats = (rows - 1) * cols + cols
        assert n_beats <= I.BUF_D

        ld_ext = (SRC + ci * 3) * I.BEAT_B      # a deliberately odd offset
        st_ext = (DST + ci * 64) * I.BEAT_B

        ld_cfg = dict(rows=rows, cols=cols, in_cnt=in_cnt,
                      in_stride=in_stride, ext_rstride=ext_rs,
                      buf_rstride=cols)
        # the store walks the same on-chip window but writes out contiguously,
        # so the check pins down the ORDER the load walked the source in
        st_cfg = dict(rows=1, cols=rows * cols, ext_rstride=rows * cols,
                      buf_rstride=rows * cols)

        b.add(I.P_MTE_IN,
              (lambda e, d, c: (lambda **kw: I.dma(I.P_MTE_IN, e, d, **c,
                                                   **kw)))(ld_ext, base,
                                                           ld_cfg),
              reads=ext_beats(ld_ext // I.BEAT_B,
                              rows * max(cols, 1) * max(in_stride, cols) + 64),
              writes=beats(base, rows * cols),
              name="ld[%d]" % ci)
        b.add(I.P_MTE_OUT,
              (lambda e, d, c: (lambda **kw: I.dma(I.P_MTE_OUT, e, d, **c,
                                                   **kw)))(st_ext, base,
                                                           st_cfg),
              reads=beats(base, rows * cols),
              writes=ext_beats(st_ext // I.BEAT_B, rows * cols),
              name="st[%d]" % ci)
        checks.append((DST + ci * 64, rows * cols))
        buf += 1

    descs = b.build()
    for _q, _m, d in descs:
        M.execute(mach, d)
    for _q, _m, d in descs:
        prog.push(d, qid=_q, mcu=_m)
    for base, n in checks:
        for i in range(n):
            prog.check(base + i, mach.mem_word(base + i))
    prog.assume(npu_sched.window())
    prog.note("dma agu: %d cases, %d descriptors" % (len(CASES), prog.n_desc))
    return prog, b.stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--seed", type=int, default=1)
    ap.add_argument("--win", type=int, default=I.WIN)
    ap.add_argument("-o", "--out", default="tests/vectors/dma.txt")
    a = ap.parse_args()
    npu_sched.set_window(a.win)
    prog, stats = gen(a.seed)
    prog.write(a.out)
    print("wrote %s: %d descriptors, %d cases, %d events"
          % (a.out, prog.n_desc, len(CASES), stats["events"]))


if __name__ == "__main__":
    main()
