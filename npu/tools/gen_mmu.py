#!/usr/bin/env python3
"""Run a program entirely through translated addresses.

Every other generator emits physical addresses, so nothing checked that the
region table is actually in the path. This one puts the tensors at virtual
addresses ABOVE the 32-bit physical window: a build that bypasses
translation cannot pass by accident, because the address it would issue does
not exist.

What each case is for:

  base          relocation at all -- a load and a store through two regions
                that map to physical pages nowhere near the virtual ones
  cross-ld      a load window that spans a page boundary inside one region.
                Two things have to hold: ppn + (vpn - vpn_base) has to carry
                into the next page, and the burst has to be clipped at the
                boundary, which AXI4 requires whether or not translation is
                on
  override      a page covered by both a large region at a high index and a
                one-page region at index 0. Lowest index wins, which is how
                a driver pins one tensor somewhere else without rebuilding
                the table
  cross-st      the same boundary case on the write side, where the address
                is latched for AW rather than driven combinationally
  long          a window longer than MAX_BURST starting mid-page, so the
                first burst is clipped by the page and the rest by MAX_BURST

Dependency tracking uses PHYSICAL beats. Two regions may alias onto the same
physical page, and the ordering the compiler emits has to be correct for the
memory that is actually written, not for the names the descriptors use.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import npu_isa as I
import npu_sched
import npu_model as M
from npu_sched import Builder, beats, ext_beats

PG = 1 << I.PG_SH                      # 4096 bytes
PGB = I.PG_BEATS                       # 128 beats

# physical pages (byte addresses)
PA_SRC = 0x0000_4000                   # 4 pages of source
PA_DST = 0x0000_8000                   # 4 pages of destination
PA_ALT = 0x0001_0000                   # the page the override points at

# virtual bases, chosen above 2**32 worth of nothing in particular so that
# an untranslated address is not a valid physical one
VA_SRC = 0x40_0000_0000               # 2**38, far outside the physical window
VA_DST = 0x60_0000_0000
VA_OVR = VA_SRC + 2 * PG               # page 2 of the source window

#       idx  va      pa       pages  r      w
REGIONS = [
    (0, VA_OVR, PA_ALT, 1, True,  False),   # override, must win over idx 2
    (2, VA_SRC, PA_SRC, 4, True,  False),   # source, read only
    (3, VA_DST, PA_DST, 4, False, True),    # destination, write only
]

# (name, va_load, cols, va_store)  -- all single-row windows
def cases():
    return [
        ("base",     VA_SRC,                        4,  VA_DST),
        ("cross-ld", VA_SRC + (PGB - 3) * I.BEAT_B, 8,  VA_DST + 16 * I.BEAT_B),
        ("override", VA_OVR,                        6,  VA_DST + 32 * I.BEAT_B),
        ("cross-st", VA_SRC + 64 * I.BEAT_B,        8,  VA_DST + (PGB - 3) * I.BEAT_B),
        ("long",     VA_SRC + (PGB - 7) * I.BEAT_B, 40, VA_DST + 2 * PG),
    ]


def gen():
    mach = M.Machine()
    prog = I.Program()
    b = Builder(verbose=False)

    # ---- configure translation, in the hardware and in the model ----
    prog.regions(REGIONS)
    for off, val in [kv for r in REGIONS for kv in I.rgn_csr(*r)]:
        mach.csr_write(off, val)
    mach.csr_write(I.CSR_MMU_CTRL, 1)

    # ---- fill every physical page the source regions can reach ----
    for base, npg in ((PA_SRC, 4), (PA_ALT, 1)):
        for i in range(npg * PGB):
            beat = base // I.BEAT_B + i
            mach.mem_set(beat, [M.sat16((beat * 7 + l * 131) % 30000)
                                for l in range(I.LANES)])
    for beat in sorted(mach.mem):
        prog.mem(beat, mach.mem_word(beat))

    checks = []
    for ci, (name, va_ld, cols, va_st) in enumerate(cases()):
        bufid = ci % I.NBUF
        base = I.addr(bufid, 0)
        assert cols <= I.BUF_D

        ld = dict(rows=1, cols=cols, ext_rstride=cols, buf_rstride=cols)
        st = dict(rows=1, cols=cols, ext_rstride=cols, buf_rstride=cols)

        pa_ld = mach.xlate(va_ld // I.BEAT_B, False)
        pa_st = mach.xlate(va_st // I.BEAT_B, True)

        b.add(I.P_MTE_IN,
              (lambda e, d, c: (lambda **kw: I.dma(I.P_MTE_IN, e, d, **c,
                                                   **kw)))(va_ld, base, ld),
              reads=ext_beats(pa_ld, cols),
              writes=beats(base, cols),
              name="ld[%s]" % name)
        b.add(I.P_MTE_OUT,
              (lambda e, d, c: (lambda **kw: I.dma(I.P_MTE_OUT, e, d, **c,
                                                   **kw)))(va_st, base, st),
              reads=beats(base, cols),
              writes=ext_beats(pa_st, cols),
              name="st[%s]" % name)
        checks.append((pa_st, cols))

    descs = b.build()
    for q, m, d in descs:
        M.execute(mach, d)
    for q, m, d in descs:
        prog.push(d, qid=q, mcu=m)
    for pa, n in checks:
        for i in range(n):
            prog.check(pa + i, mach.mem_word(pa + i))
    prog.assume(npu_sched.window())
    prog.note("mmu: %d cases, %d regions, %d descriptors"
              % (len(cases()), len(REGIONS), prog.n_desc))
    return prog, b.stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--win", type=int, default=I.WIN)
    ap.add_argument("-o", "--out", default="tests/vectors/mmu.txt")
    a = ap.parse_args()
    npu_sched.set_window(a.win)
    prog, stats = gen()
    prog.write(a.out)
    print("wrote %s: %d descriptors, %d cases, %d events"
          % (a.out, prog.n_desc, len(cases()), stats["events"]))


if __name__ == "__main__":
    main()
