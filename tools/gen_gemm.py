#!/usr/bin/env python3
"""Blocked GEMM generator.

    C[M,N] = A[M,K] . B[K,N]

CUBE computes C += A^T.B over a 16x16 output tile, consuming one beat of
each operand per cycle, so both operands must be K-contiguous. A is
therefore held transposed in external memory (SEG layout: K rows of M
values); B is already in that orientation. This is the layout decision the
whole kernel is built around -- see docs/spec_layout.md.

Three things make it run:

  double buffering   the next K block is fetched while the current one is
                     multiplied, in the other half of each operand buffer
  accumulator relay  acc_cont / acc_hold keep the partial sum inside the
                     MAC array across descriptors, so a K larger than a
                     buffer never spills to memory
  staged events      the event count is a property of the pipeline depth,
                     not of the problem size: eight live events cover any
                     M, N, K. On a single queue the message queue delivers
                     in program order, so events recycle without a barrier.

A and B are laid out so each operand stream is one contiguous run per
K block, which is what lets a whole block arrive in one AXI burst chain.
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import npu_isa as I
import npu_model as M
from npu_sched import Builder, beats

L = I.LANES


def gen(m, n, k, kb, fp, seed, shift):
    assert m % L == 0 and n % L == 0 and k % L == 0
    assert kb <= 128 and k % kb == 0
    mt, nt = m // L, n // L
    rng = random.Random(seed)
    mach = M.Machine()
    prog = I.Program()

    # ---- external layout, in beats: SEG, i.e. tile-major ----
    #   A^T : beat(mi, k_) = AT + mi*k + k_     K contiguous per tile
    #   B   : beat(ni, k_) = B0 + ni*k + k_
    #   C   : beat(ni, r ) = C0 + ni*m + r      M contiguous per column tile
    #
    # Laying the reduction axis out contiguously is what turns each operand
    # stream into one long burst chain instead of k single-beat transfers.
    # The same data in the obvious row-major order costs about an order of
    # magnitude in effective bandwidth here, which is the whole argument for
    # letting the compiler own the layout.
    AT = 0
    B0 = AT + mt * k
    C0 = B0 + nt * k

    def rnd():
        return (M.f_to_bf(rng.uniform(-1.0, 1.0)) if fp
                else M.sat16(rng.randint(-100, 100)))

    for kk in range(k):
        for mi in range(mt):
            mach.mem_set(AT + mi * k + kk, [rnd() for _ in range(L)])
        for ni in range(nt):
            mach.mem_set(B0 + ni * k + kk, [rnd() for _ in range(L)])
    for b in sorted(mach.mem):
        prog.mem(b, mach.mem_word(b))

    # ---- on-chip allocation ----
    # Buffer 0 holds the whole K of one A tile, resident across the entire
    # ni sweep. Buffer 1 is split in two halves so the next B block streams
    # in while the current one is multiplied. Buffer 2 holds the output tile.
    #
    # Residency is the whole game for bandwidth. A 16x16 tile has an
    # arithmetic intensity of 8 while the machine's balance point is 16, so
    # on paper it is a factor of two short. Keeping one side resident closes
    # the gap on its own: traffic becomes (1 + 1/nt) beats per MAC cycle,
    # which is 1.06 at nt = 16. Adding MACs would not have helped.
    assert k <= I.BUF_D, "A tile must fit one buffer to stay resident"
    HALF = 128
    ABUF = I.addr(0, 0)
    CBUF = I.addr(2, 0)

    def bbuf(h):
        return I.addr(1, h * HALF)

    b = Builder(single_queue=True, verbose=True)
    nblk = k // kb
    par = 0

    for mi in range(mt):
        # A tile mi, all of K, loaded once and reused for every ni
        aext = (AT + mi * k) * I.BEAT_B
        b.add(I.P_MTE_IN,
              (lambda e: (lambda **kw: I.dma(
                  I.P_MTE_IN, e, ABUF, 1, k, **kw)))(aext),
              writes=beats(ABUF, k), name="ldA[%d]" % mi)

        for ni in range(nt):
            for kbi in range(nblk):
                par += 1
                h = par & 1
                k0 = kbi * kb
                bext = (B0 + ni * k + k0) * I.BEAT_B
                bd = bbuf(h)
                b.add(I.P_MTE_IN,
                      (lambda e, d: (lambda **kw: I.dma(
                          I.P_MTE_IN, e, d, 1, kb, **kw)))(bext, bd),
                      writes=beats(bd, kb), name="ldB[%d,%d]" % (ni, kbi))

                cont = 1 if kbi > 0 else 0
                hold = 1 if kbi < nblk - 1 else 0
                b.add(I.P_CUBE,
                      (lambda sa, sb, c_, h_: (lambda **kw: I.mm(
                          sa, sb, CBUF, kb, shift=shift, acc_cont=c_,
                          acc_hold=h_, fp=int(fp), **kw)))(
                              ABUF + k0, bd, cont, hold),
                      reads=beats(ABUF + k0, kb) | beats(bd, kb),
                      writes=(set() if hold else beats(CBUF, L)),
                      name="mm[%d,%d,%d]" % (mi, ni, kbi))

            cext = (C0 + ni * m + mi * L) * I.BEAT_B
            b.add(I.P_MTE_OUT,
                  (lambda e: (lambda **kw: I.dma(
                      I.P_MTE_OUT, e, CBUF, 1, L, **kw)))(cext),
                  reads=beats(CBUF, L), name="stC[%d,%d]" % (mi, ni))

    descs = b.build()
    for _q, _m, d in descs:
        M.execute(mach, d)
    for _q, _m, d in descs:
        prog.push(d, qid=_q, mcu=_m)
    for ni in range(nt):
        for r in range(m):
            prog.check(C0 + ni * m + r, mach.mem_word(C0 + ni * m + r))

    ideal = mt * nt * k                       # one beat pair per cycle
    prog.note("gemm M=%d N=%d K=%d kb=%d fp=%d ideal_cycles=%d"
              % (m, n, k, kb, int(fp), ideal))
    return prog, b.stats, ideal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-M", type=int, default=32)
    ap.add_argument("-N", type=int, default=32)
    ap.add_argument("-K", type=int, default=64)
    ap.add_argument("--kb", type=int, default=32,
                    help="K block in beats; <= 128 and a divisor of K")
    ap.add_argument("--fp", action="store_true")
    ap.add_argument("-s", "--seed", type=int, default=1)
    ap.add_argument("--shift", type=int, default=10)
    ap.add_argument("-o", "--out", default="tests/vectors/gemm.txt")
    a = ap.parse_args()
    prog, stats, ideal = gen(a.M, a.N, a.K, a.kb, a.fp, a.seed, a.shift)
    prog.write(a.out)
    print("wrote %s: %d descriptors (%d sync no-ops), %d events, "
          "ideal %d cycles" % (a.out, prog.n_desc, stats["nops"],
                               stats["events"], ideal))


if __name__ == "__main__":
    main()
