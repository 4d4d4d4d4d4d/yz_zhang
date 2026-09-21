#!/usr/bin/env python3
"""Random program generator: cross-checks the RTL against the model.

Emits a legal program that touches every pipe and every VEC opcode class,
computes the expected external memory with npu_model, and writes the whole
thing as a tb_npu_prog program. Any disagreement between the model and the
RTL shows up as a failing check line.

Descriptors are spread across queues and MCU ports on purpose: the
scheduler is free to reorder anything the event graph does not pin down, so
a run that only passes in program order fails here.
"""
import argparse
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import npu_isa as I
import npu_model as M
from npu_sched import Builder, beats

VEC_POOL_INT = [I.V_MOV, I.V_ADDI, I.V_MULI, I.V_MAXI, I.V_ADD, I.V_SUB,
                I.V_MUL, I.V_MAX, I.V_MIN, I.V_BRC_R, I.V_BRC_C,
                I.V_RED_SUM, I.V_RED_MAX, I.V_SEL, I.V_SELD, I.V_CVT_I2F]
VEC_POOL_FP = [I.V_MOV, I.V_ADDI, I.V_MULI, I.V_MAXI, I.V_ADD, I.V_SUB,
               I.V_MUL, I.V_MAX, I.V_MIN, I.V_BRC_R, I.V_BRC_C,
               I.V_RED_SUM, I.V_RED_MAX, I.V_LUT, I.V_RECIP, I.V_SEL,
               I.V_SELD, I.V_CVT_F2I]


def rand_beat(rng, fp):
    lanes = []
    for _ in range(I.LANES):
        if fp:
            lanes.append(M.f_to_bf(rng.uniform(-4.0, 4.0)))
        else:
            lanes.append(M.sat16(rng.randint(-120, 120)))
    return lanes


def gen(seed, fp, n_vec, only=None):
    rng = random.Random(seed)
    mach = M.Machine()
    prog = I.Program()

    K = 16
    EXT_A, EXT_B, EXT_T, EXT_OUT = 0, 64, 128, 256

    # ---- external memory image ----
    for i in range(K):
        mach.mem_set(EXT_A + i, rand_beat(rng, fp))
        mach.mem_set(EXT_B + i, rand_beat(rng, fp))
    for i in range(2):
        mach.mem_set(EXT_T + i, rand_beat(rng, fp))
    for beat in sorted(mach.mem):
        prog.mem(beat, mach.mem_word(beat))

    A0, B0, C0, D0 = I.addr(0, 0), I.addr(1, 0), I.addr(2, 0), I.addr(3, 0)
    T0 = I.addr(1, 64)                      # LUT table / broadcast vector
    b = Builder(verbose=True)
    nq, nmcu = 4, I.NMCU

    def q(i):
        return i % nq

    def m(i):
        return i % nmcu

    step = 0

    def nxt():
        nonlocal step
        step += 1
        return step

    s = nxt()
    b.add(I.P_MTE_IN,
          lambda **k: I.dma(I.P_MTE_IN, EXT_A * I.BEAT_B, A0, 1, K, **k),
          writes=beats(A0, K), qid=q(s), mcu=m(s), name="load A")
    s = nxt()
    b.add(I.P_MTE_IN,
          lambda **k: I.dma(I.P_MTE_IN, EXT_B * I.BEAT_B, B0, 1, K, **k),
          writes=beats(B0, K), qid=q(s), mcu=m(s), name="load B")
    s = nxt()
    b.add(I.P_MTE_IN,
          lambda **k: I.dma(I.P_MTE_IN, EXT_T * I.BEAT_B, T0, 1, 2, **k),
          writes=beats(T0, 2), qid=q(s), mcu=m(s), name="load table")

    # ---- one matrix multiply ----
    shift = 10 if not fp else 0
    s = nxt()
    b.add(I.P_CUBE,
          lambda **k: I.mm(A0, B0, C0, K, shift=shift, fp=int(fp), **k),
          reads=beats(A0, K) | beats(B0, K), writes=beats(C0, I.LANES),
          qid=q(s), mcu=m(s), name="mm")

    # ---- a chain of vector ops, ping-ponging between two regions ----
    pool = ([only] if only is not None
            else (VEC_POOL_FP if fp else VEC_POOL_INT))
    src, dst = C0, D0
    live = I.LANES
    for v in range(n_vec):
        opc = pool[v % len(pool)]
        rows = I.LANES
        src_b = T0
        subop = rng.choice([I.SUB_ADD, I.SUB_SUB, I.SUB_MUL, I.SUB_MAX])
        imm = 0
        mask = 0xFFFF
        if opc in (I.V_ADDI, I.V_MAXI):
            imm = M.f_to_bf(rng.uniform(-2, 2)) if fp else \
                  M.sat16(rng.randint(-50, 50))
        elif opc == I.V_MULI:
            imm = (M.f_to_bf(rng.uniform(-2, 2)) if fp
                   else M.sat16(rng.randint(-8, 8))) | (0 if fp else (6 << 16))
        elif opc in (I.V_MUL,):
            imm = 0 if fp else (10 << 16)
        elif opc == I.V_RED_SUM:
            imm = 0 if fp else (4 << 16)
        elif opc == I.V_LUT:
            imm = (M.f_to_bf(-4.0) & 0xFFFF) | (1 << 16)
        elif opc in (I.V_CVT_F2I, I.V_CVT_I2F):
            imm = 6 << 16
        elif opc == I.V_SEL:
            mask = rng.randint(1, 0xFFFF)
        if opc in (I.V_ADD, I.V_SUB, I.V_MUL, I.V_MAX, I.V_MIN, I.V_SELD):
            src_b = C0 if src != C0 else D0

        # reductions write ceil(rows/16) beats
        n_out = (rows + I.LANES - 1) // I.LANES if opc in (
            I.V_RED_SUM, I.V_RED_MAX) else rows
        rd = beats(src, rows)
        if opc in (I.V_ADD, I.V_SUB, I.V_MUL, I.V_MAX, I.V_MIN, I.V_SELD):
            rd |= beats(src_b, rows)
        elif opc == I.V_BRC_R:
            rd |= beats(src_b, 1)
        elif opc == I.V_BRC_C:
            rd |= beats(src_b, 1)
        elif opc == I.V_LUT:
            rd |= beats(src_b, 2)
        # a predicated write leaves the untouched lanes alone, so the
        # destination is also read
        wr = beats(dst, n_out)
        if mask != 0xFFFF or opc == I.V_SELD or opc in (I.V_RED_SUM,
                                                        I.V_RED_MAX):
            rd |= wr

        s = nxt()
        b.add(I.P_VEC,
              (lambda o, sa, sb, dd, rr, mm_, im, su: (
                  lambda **k: I.vop(o, sa, dd, rr, src_b=sb, mask=mm_,
                                    imm=im, subop=su, fp=int(fp), **k)))(
                  opc, src, src_b, dst, rows, mask, imm, subop),
              reads=rd, writes=wr, qid=q(s), mcu=m(s),
              name="vec %s" % I.VEC_NAMES[opc])
        live = n_out
        src, dst = dst, src

    # ---- transpose the live result, then store it ----
    TR = I.addr(0, 128)
    s = nxt()
    b.add(I.P_FIX, lambda **k: I.trans(src, TR, 1, **k),
          reads=beats(src, I.LANES), writes=beats(TR, I.LANES),
          qid=q(s), mcu=m(s), name="transpose")

    s = nxt()
    b.add(I.P_MTE_OUT,
          lambda **k: I.dma(I.P_MTE_OUT, EXT_OUT * I.BEAT_B, TR, 1,
                            I.LANES, **k),
          reads=beats(TR, I.LANES), qid=q(s), mcu=m(s), name="store")

    descs = b.build()

    # ---- reference run ----
    for _qid, _mcu, d in descs:
        M.execute(mach, d)

    for _qid, _mcu, d in descs:
        prog.push(d, qid=_qid, mcu=_mcu)
    for i in range(I.LANES):
        prog.check(EXT_OUT + i, mach.mem_word(EXT_OUT + i))
    prog.note("random seed=%d fp=%d vec_ops=%d live_beats=%d"
              % (seed, int(fp), n_vec, live))
    return prog, b.stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--seed", type=int, default=1)
    ap.add_argument("--fp", action="store_true", help="bf16 instead of int16")
    ap.add_argument("-n", "--vec-ops", type=int, default=18)
    ap.add_argument("-o", "--out", default="tests/vectors/random.txt")
    ap.add_argument("--op", help="repeat a single VEC opcode by name")
    a = ap.parse_args()
    only = None
    if a.op:
        names = {v: k for k, v in I.VEC_NAMES.items()}
        if a.op not in names:
            raise SystemExit("unknown opcode %s; one of: %s"
                             % (a.op, " ".join(sorted(names))))
        only = names[a.op]
    prog, stats = gen(a.seed, a.fp, a.vec_ops, only)
    prog.write(a.out)
    print("wrote %s: %d descriptors (%d sync no-ops), %d events"
          % (a.out, prog.n_desc, stats["nops"], stats["events"]))


if __name__ == "__main__":
    main()
