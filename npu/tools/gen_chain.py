#!/usr/bin/env python3
"""Dependency turnaround microbenchmark.

A chain of N dependent ops doing the minimum possible work (one beat each),
each waiting on the event the previous one sets. The body is one cycle, so
cycles per op is almost entirely the cost of ONE dependency edge:

    unit finishes -> completion -> semaphore increment -> the scheduler can
    see it -> issue -> the unit pops it -> first operand read

That number bounds how fast any serial chain can run, and a serial chain is
what a softmax or a LayerNorm is. On the encoder layer 87% of all cycles are
spent stalled on a dependency, so this is the number that decides whether
the layer is worth optimising in hardware or in the compiler.

--same-pipe keeps the chain on one pipe (the compiler then gets the ordering
for free from the (pipe, queue) FIFO and needs no events at all); the
default alternates pipes so every edge really costs an event.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import npu_isa as I
import npu_sched
import npu_model as M
from npu_sched import Builder, beats, ext_beats


def gen(n, same_pipe, use_events):
    mach = M.Machine()
    prog = I.Program()
    for i in range(4):
        mach.mem_set(i, [M.sat16(i * 16 + l) for l in range(I.LANES)])
    for b in sorted(mach.mem):
        prog.mem(b, mach.mem_word(b))

    A = I.addr(0, 0)
    b = Builder(single_queue=True, verbose=False)
    b.add(I.P_MTE_IN,
          lambda **k: I.dma(I.P_MTE_IN, 0, A, 1, 2, **k),
          reads=ext_beats(0, 2), writes=beats(A, 2), name="load")

    # ping-pong between two beats so every op depends on the previous one
    src, dst = A, A + 1
    for i in range(n):
        if same_pipe or not use_events:
            pipe = I.P_VEC
        else:
            pipe = I.P_VEC if (i & 1) == 0 else I.P_FIX
        if pipe == I.P_VEC:
            b.add(I.P_VEC,
                  (lambda s_, d_: (lambda **k: I.vop(I.V_ADDI, s_, d_, 1,
                                                     imm=1, **k)))(src, dst),
                  reads=beats(src, 1), writes=beats(dst, 1), name="v%d" % i)
        else:
            # a one-tile transpose is the cheapest FIX op; it needs 16 beats
            b.add(I.P_FIX,
                  (lambda s_, d_: (lambda **k: I.trans(s_, d_, 1, **k)))(
                      I.addr(0, 16), I.addr(0, 32)),
                  reads=beats(I.addr(0, 16), 16),
                  writes=beats(I.addr(0, 32), 16), name="f%d" % i)
        if pipe == I.P_VEC:
            src, dst = dst, src

    b.add(I.P_MTE_OUT,
          (lambda s_: (lambda **k: I.dma(I.P_MTE_OUT, 64 * I.BEAT_B, s_, 1, 1,
                                         **k)))(src),
          reads=beats(src, 1), writes=ext_beats(64, 1), name="store")

    descs = b.build()
    for _q, _m, d in descs:
        M.execute(mach, d)
    for _q, _m, d in descs:
        prog.push(d, qid=_q, mcu=_m)
    prog.check(64, mach.mem_word(64))
    prog.assume(npu_sched.window())
    prog.note("chain n=%d same_pipe=%d ops=%d" % (n, int(same_pipe),
                                                  prog.n_desc))
    return prog, b.stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=64, help="chain length")
    ap.add_argument("--same-pipe", action="store_true",
                    help="keep the chain on one pipe: ordering comes from the "
                         "(pipe,queue) FIFO and no event is needed")
    ap.add_argument("--win", type=int, default=I.WIN)
    ap.add_argument("-o", "--out", default="tests/vectors/chain.txt")
    a = ap.parse_args()
    npu_sched.set_window(a.win)
    prog, stats = gen(a.n, a.same_pipe, True)
    prog.write(a.out)
    print("wrote %s: %d descriptors, %d events, %d sync no-ops"
          % (a.out, prog.n_desc, stats["events"], stats["nops"]))


if __name__ == "__main__":
    main()
