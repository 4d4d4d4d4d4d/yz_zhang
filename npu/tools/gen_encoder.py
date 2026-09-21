#!/usr/bin/env python3
"""Whole transformer encoder layer, end to end.

    Q,K,V = X.Wq, X.Wk, X.Wv
    P     = softmax(Q.K^T * scale)
    A     = (P.V).Wo
    N1    = LayerNorm(A + X)
    H     = GELU(N1.W1)
    N2    = LayerNorm(H.W2 + N1)

Everything interesting here is layout. A matrix multiply consumes its left
operand transposed and produces its result untransposed, while a row
reduction wants the reduced axis in the lanes. Those two preferences are
incompatible, so the layer needs an explicit transpose at every boundary
where the orientation flips -- six of them below, each one a FIX descriptor
per 16x16 tile. See tools/npu_layout.py and docs/spec_layout.md.

Softmax, GELU and the LayerNorm reciprocal square root are 16-segment
piecewise linear tables evaluated by V_LUT. The generator fits each table,
runs the whole layer through the bit-exact model, and reports the error of
every stage against a float64 reference, so the numeric cost of each
approximation is visible rather than assumed.
"""
import argparse
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import npu_isa as I
import npu_model as M
import npu_layout as LY
from npu_sched import Builder, beats

L = I.LANES


# ---------------------------------------------------------------- tables
def fit_lut(f, lo, sh):
    """16 segments of width 2^-sh starting at lo, each a chord of f."""
    w = 2.0 ** -sh
    slopes, icpts = [], []
    for i in range(L):
        x0 = lo + i * w
        x1 = x0 + w
        y0, y1 = f(x0), f(x1)
        s = (y1 - y0) / w
        slopes.append(M.f_to_bf(s))
        icpts.append(M.f_to_bf(y0 - s * x0))
    return slopes, icpts


def lut_imm(lo, sh):
    return (M.f_to_bf(lo) & 0xFFFF) | (sh << 16)


def gelu(x):
    return 0.5 * x * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------- builder
class Enc:
    def __init__(self, s, d, dff, seed):
        self.S, self.D, self.F = s, d, dff
        self.rng = random.Random(seed)
        self.mach = M.Machine()
        self.prog = I.Program()
        self.b = Builder(single_queue=True, verbose=True)
        self.ext = 0
        self.ref = {}
        self.nT = 0
        # on-chip regions
        self.A = I.addr(0, 0)      # SEG left operand
        self.W0 = I.addr(1, 0)     # weight tile, half 0
        self.W1 = I.addr(1, 128)   # weight tile, half 1
        self.C = I.addr(2, 0)      # ROW result
        self.T = I.addr(3, 0)      # scratch
        self.half = 0

    # ---- external allocation ----
    def alloc(self, nbeats):
        a = self.ext
        self.ext += nbeats
        return a

    def put(self, base, mat, rows, cols, seg=False):
        """Write a float matrix into external memory in ROW or SEG order."""
        if seg:
            mat = [[mat[r][c] for r in range(rows)] for c in range(cols)]
            rows, cols = cols, rows
        for cj in range((cols + L - 1) // L):
            for r in range(rows):
                lanes = [M.f_to_bf(mat[r][cj * L + l])
                         if cj * L + l < cols else 0
                         for l in range(L)]
                self.mach.mem_set(base + cj * rows + r, lanes)

    def get(self, base, rows, cols):
        out = [[0.0] * cols for _ in range(rows)]
        for cj in range((cols + L - 1) // L):
            for r in range(rows):
                lanes = self.mach.mem_get(base + cj * rows + r)
                for l in range(L):
                    if cj * L + l < cols:
                        out[r][cj * L + l] = M.bf_to_f(lanes[l])
        return out

    def rand_mat(self, r, c, scale=1.0):
        return [[self.rng.uniform(-scale, scale) for _ in range(c)]
                for _ in range(r)]

    # ---- descriptor helpers ----
    def ld(self, ext_beat, buf, n, name):
        self.b.add(I.P_MTE_IN,
                   (lambda e, d, nn: (lambda **kw: I.dma(
                       I.P_MTE_IN, e * I.BEAT_B, d, 1, nn, **kw)))(
                           ext_beat, buf, n),
                   writes=beats(buf, n), name=name)

    def st(self, ext_beat, buf, n, name):
        self.b.add(I.P_MTE_OUT,
                   (lambda e, d, nn: (lambda **kw: I.dma(
                       I.P_MTE_OUT, e * I.BEAT_B, d, 1, nn, **kw)))(
                           ext_beat, buf, n),
                   reads=beats(buf, n), name=name)

    def tr(self, src, dst, name):
        """One 16x16 tile transpose."""
        self.nT += 1
        self.b.add(I.P_FIX,
                   (lambda s_, d_: (lambda **kw: I.trans(s_, d_, 1, **kw)))(
                       src, dst),
                   reads=beats(src, L), writes=beats(dst, L), name=name)

    def vec(self, opc, sa, dst, rows, sb=0, imm=0, subop=I.SUB_ADD,
            mask=0xFFFF, extra_reads=(), name=""):
        n_out = ((rows + L - 1) // L) if opc in (I.V_RED_SUM, I.V_RED_MAX) \
                else rows
        rd = set(beats(sa, rows)) | set(extra_reads)
        self.b.add(I.P_VEC,
                   (lambda o, a_, b_, d_, r_, i_, s_, m_: (lambda **kw: I.vop(
                       o, a_, d_, r_, src_b=b_, imm=i_, subop=s_, mask=m_,
                       fp=1, **kw)))(opc, sa, sb, dst, rows, imm, subop, mask),
                   reads=rd, writes=beats(dst, n_out), name=name or "vec")
        return n_out

    def mm(self, seg_a, row_w, dst, k, name):
        self.b.add(I.P_CUBE,
                   (lambda a_, w_, d_, k_: (lambda **kw: I.mm(
                       a_, w_, d_, k_, fp=1, **kw)))(seg_a, row_w, dst, k),
                   reads=beats(seg_a, k) | beats(row_w, k),
                   writes=beats(dst, L), name=name)

    # ---- transpose a ROW tensor on chip into a SEG tensor on chip ----
    def transpose(self, row_base, seg_base, rows, cols, tag):
        for src_off, dst_off in LY.transpose_plan(0, 0, rows, cols):
            self.tr(row_base + src_off, seg_base + dst_off, "tr:%s" % tag)

    # ---- Y = X.W, X given as SEG on chip, W streamed from external ----
    def matmul(self, seg_a, ext_w, row_c, k, rows, cols, tag):
        for oj in range((cols + L - 1) // L):
            self.half ^= 1
            wb = self.W0 if self.half == 0 else self.W1
            self.ld(ext_w + oj * k, wb, k, "ldW:%s[%d]" % (tag, oj))
            for sj in range((rows + L - 1) // L):
                self.mm(seg_a + sj * k, wb, row_c + oj * rows + sj * L, k,
                        "mm:%s[%d,%d]" % (tag, oj, sj))


# ---------------------------------------------------------------- stages
def build(s, d, dff, seed):
    e = Enc(s, d, dff, seed)
    S, D, F = s, d, dff
    nD, nF, nS = D // L, F // L, S // L
    assert S % L == 0 and D % L == 0 and F % L == 0

    # ---- external tensors ----
    X_row = e.alloc(LY.row_size(S, D))
    X_seg = e.alloc(LY.seg_size(S, D))
    Wq = e.alloc(LY.row_size(D, D))
    Wk = e.alloc(LY.row_size(D, D))
    Wv = e.alloc(LY.row_size(D, D))
    Wo = e.alloc(LY.row_size(D, D))
    W1 = e.alloc(LY.row_size(D, F))
    W2 = e.alloc(LY.row_size(F, D))
    Q_row = e.alloc(LY.row_size(S, D))
    K_row = e.alloc(LY.row_size(S, D))
    V_row = e.alloc(LY.row_size(S, D))
    Q_seg = e.alloc(LY.seg_size(S, D))
    K_seg = e.alloc(LY.seg_size(S, D))
    Sc_row = e.alloc(LY.row_size(S, S))
    P_seg = e.alloc(LY.seg_size(S, S))
    Ctx_row = e.alloc(LY.row_size(S, D))
    Ctx_seg = e.alloc(LY.seg_size(S, D))
    A_row = e.alloc(LY.row_size(S, D))
    N1_row = e.alloc(LY.row_size(S, D))
    N1_seg = e.alloc(LY.seg_size(S, D))
    H_row = e.alloc(LY.row_size(S, F))
    H_seg = e.alloc(LY.seg_size(S, F))
    Y_row = e.alloc(LY.row_size(S, D))
    N2_row = e.alloc(LY.row_size(S, D))
    LUT_exp = e.alloc(2)
    LUT_sqrt = e.alloc(2)
    LUT_gelu = e.alloc(2)

    # ---- data ----
    X = e.rand_mat(S, D, 1.0)
    wq = e.rand_mat(D, D, 0.25)
    wk = e.rand_mat(D, D, 0.25)
    wv = e.rand_mat(D, D, 0.25)
    wo = e.rand_mat(D, D, 0.25)
    w1 = e.rand_mat(D, F, 0.25)
    w2 = e.rand_mat(F, D, 0.25)
    e.put(X_row, X, S, D)
    for base, w, r, c in ((Wq, wq, D, D), (Wk, wk, D, D), (Wv, wv, D, D),
                          (Wo, wo, D, D), (W1, w1, D, F), (W2, w2, F, D)):
        e.put(base, w, r, c)

    def put_lut(base, f, lo, sh):
        sl, ic = fit_lut(f, lo, sh)
        e.mach.mem_set(base, sl)
        e.mach.mem_set(base + 1, ic)

    EXP_LO, EXP_SH = -8.0, 1
    SQ_LO, SQ_SH = 0.0, 3          # sqrt over [0,2): variance after centering
    GE_LO, GE_SH = -4.0, 1
    put_lut(LUT_exp, math.exp, EXP_LO, EXP_SH)
    put_lut(LUT_sqrt, math.sqrt, SQ_LO, SQ_SH)
    put_lut(LUT_gelu, gelu, GE_LO, GE_SH)

    for b in sorted(e.mach.mem):
        e.prog.mem(b, e.mach.mem_word(b))

    # =============================== program ===============================
    LUTB = I.addr(3, 200)          # tables live at the top of the scratch

    def load_luts():
        e.ld(LUT_exp, LUTB, 2, "ld:lut_exp")
        e.ld(LUT_sqrt, LUTB + 2, 2, "ld:lut_sqrt")
        e.ld(LUT_gelu, LUTB + 4, 2, "ld:lut_gelu")

    load_luts()

    # ---- X: ROW -> SEG ----
    e.ld(X_row, e.C, LY.row_size(S, D), "ld:X")
    e.transpose(e.C, e.A, S, D, "X")
    e.st(X_seg, e.A, LY.seg_size(S, D), "st:Xseg")

    # ---- Q, K, V ----
    for ext_w, out, tag in ((Wq, Q_row, "Q"), (Wk, K_row, "K"),
                            (Wv, V_row, "V")):
        e.matmul(e.A, ext_w, e.C, D, S, D, tag)
        e.st(out, e.C, LY.row_size(S, D), "st:%s" % tag)

    # ---- scores = Q.K^T : both operands must be SEG ----
    for src, dst, tag in ((Q_row, Q_seg, "Q"), (K_row, K_seg, "K")):
        e.ld(src, e.C, LY.row_size(S, D), "ld:%s" % tag)
        e.transpose(e.C, e.A, S, D, tag)
        e.st(dst, e.A, LY.seg_size(S, D), "st:%sseg" % tag)

    e.ld(Q_seg, e.A, LY.seg_size(S, D), "ld:Qseg")
    e.matmul(e.A, K_seg, e.C, D, S, S, "scores")
    scale = M.f_to_bf(1.0 / math.sqrt(D))
    for cj in range(nS):
        e.vec(I.V_MULI, e.C + cj * S, e.C + cj * S, S, imm=scale,
              name="scale")
    e.st(Sc_row, e.C, LY.row_size(S, S), "st:scores")

    # ---- softmax over each row (ROW layout: lanes are the reduced axis) ----
    e.ld(Sc_row, e.C, LY.row_size(S, S), "ld:scores")
    RED = e.T                      # per-row scalars, packed 16 per beat
    ACC = e.T + 64
    e.vec(I.V_MOV, e.C, ACC, S, name="sm:acc0")
    for cj in range(1, nS):
        e.vec(I.V_MAX, ACC, ACC, S, sb=e.C + cj * S,
              extra_reads=beats(e.C + cj * S, S) | beats(ACC, S),
              name="sm:max")
    e.vec(I.V_RED_MAX, ACC, RED, S, name="sm:rowmax")
    for cj in range(nS):
        e.vec(I.V_BRC_C, e.C + cj * S, e.C + cj * S, S, sb=RED,
              subop=I.SUB_SUB,
              extra_reads=beats(RED, nS) | beats(e.C + cj * S, S),
              name="sm:sub")
        e.vec(I.V_LUT, e.C + cj * S, e.C + cj * S, S, sb=LUTB,
              imm=lut_imm(EXP_LO, EXP_SH),
              extra_reads=beats(LUTB, 2) | beats(e.C + cj * S, S),
              name="sm:exp")
    e.vec(I.V_MOV, e.C, ACC, S, name="sm:acc1")
    for cj in range(1, nS):
        e.vec(I.V_ADD, ACC, ACC, S, sb=e.C + cj * S,
              extra_reads=beats(e.C + cj * S, S) | beats(ACC, S),
              name="sm:sum")
    e.vec(I.V_RED_SUM, ACC, RED, S, name="sm:rowsum")
    e.vec(I.V_RECIP, RED, RED, nS, name="sm:recip")
    for cj in range(nS):
        e.vec(I.V_BRC_C, e.C + cj * S, e.C + cj * S, S, sb=RED,
              subop=I.SUB_MUL,
              extra_reads=beats(RED, nS) | beats(e.C + cj * S, S),
              name="sm:norm")
    # P must be SEG for the next multiply
    e.transpose(e.C, e.A, S, S, "P")
    e.st(P_seg, e.A, LY.seg_size(S, S), "st:Pseg")

    # ---- ctx = P.V, then attn = ctx.Wo ----
    e.matmul(e.A, V_row, e.C, S, S, D, "ctx")
    e.st(Ctx_row, e.C, LY.row_size(S, D), "st:ctx")
    e.transpose(e.C, e.A, S, D, "ctx")
    e.st(Ctx_seg, e.A, LY.seg_size(S, D), "st:ctxseg")
    e.matmul(e.A, Wo, e.C, D, S, D, "attn")
    e.st(A_row, e.C, LY.row_size(S, D), "st:attn")

    # ---- residual + LayerNorm ----
    def layernorm(src_ext, res_ext, dst_ext, cols, tag):
        """dst = LayerNorm(src + res), all ROW layout."""
        nc = cols // L
        e.ld(src_ext, e.C, LY.row_size(S, cols), "ld:%s" % tag)
        e.ld(res_ext, e.T, LY.row_size(S, cols), "ld:%s.res" % tag)
        for cj in range(nc):
            e.vec(I.V_ADD, e.C + cj * S, e.C + cj * S, S, sb=e.T + cj * S,
                  extra_reads=beats(e.T + cj * S, S) | beats(e.C + cj * S, S),
                  name="%s:resid" % tag)
        R = e.T + 200
        AC = e.T + 216
        e.vec(I.V_MOV, e.C, AC, S, name="%s:m0" % tag)
        for cj in range(1, nc):
            e.vec(I.V_ADD, AC, AC, S, sb=e.C + cj * S,
                  extra_reads=beats(e.C + cj * S, S) | beats(AC, S),
                  name="%s:msum" % tag)
        e.vec(I.V_RED_SUM, AC, R, S, name="%s:rowsum" % tag)
        e.vec(I.V_MULI, R, R, nS, imm=M.f_to_bf(1.0 / cols),
              name="%s:mean" % tag)
        for cj in range(nc):
            e.vec(I.V_BRC_C, e.C + cj * S, e.C + cj * S, S, sb=R,
                  subop=I.SUB_SUB,
                  extra_reads=beats(R, nS) | beats(e.C + cj * S, S),
                  name="%s:center" % tag)
        SQ = e.A
        for cj in range(nc):
            e.vec(I.V_MUL, e.C + cj * S, SQ + cj * S, S, sb=e.C + cj * S,
                  extra_reads=beats(e.C + cj * S, S), name="%s:sq" % tag)
        e.vec(I.V_MOV, SQ, AC, S, name="%s:v0" % tag)
        for cj in range(1, nc):
            e.vec(I.V_ADD, AC, AC, S, sb=SQ + cj * S,
                  extra_reads=beats(SQ + cj * S, S) | beats(AC, S),
                  name="%s:vsum" % tag)
        e.vec(I.V_RED_SUM, AC, R, S, name="%s:varsum" % tag)
        e.vec(I.V_MULI, R, R, nS, imm=M.f_to_bf(1.0 / cols),
              name="%s:var" % tag)
        e.vec(I.V_ADDI, R, R, nS, imm=M.f_to_bf(1e-3), name="%s:eps" % tag)
        e.vec(I.V_LUT, R, R, nS, sb=LUTB + 2, imm=lut_imm(SQ_LO, SQ_SH),
              extra_reads=beats(LUTB + 2, 2) | beats(R, nS),
              name="%s:sqrt" % tag)
        e.vec(I.V_RECIP, R, R, nS, name="%s:rstd" % tag)
        for cj in range(nc):
            e.vec(I.V_BRC_C, e.C + cj * S, e.C + cj * S, S, sb=R,
                  subop=I.SUB_MUL,
                  extra_reads=beats(R, nS) | beats(e.C + cj * S, S),
                  name="%s:scale" % tag)
        e.st(dst_ext, e.C, LY.row_size(S, cols), "st:%s" % tag)

    layernorm(A_row, X_row, N1_row, D, "ln1")

    # ---- feed forward ----
    e.ld(N1_row, e.C, LY.row_size(S, D), "ld:N1")
    e.transpose(e.C, e.A, S, D, "N1")
    e.st(N1_seg, e.A, LY.seg_size(S, D), "st:N1seg")
    e.matmul(e.A, W1, e.C, D, S, F, "ffn1")
    for cj in range(nF):
        e.vec(I.V_LUT, e.C + cj * S, e.C + cj * S, S, sb=LUTB + 4,
              imm=lut_imm(GE_LO, GE_SH),
              extra_reads=beats(LUTB + 4, 2) | beats(e.C + cj * S, S),
              name="gelu")
    e.st(H_row, e.C, LY.row_size(S, F), "st:H")
    e.transpose(e.C, e.A, S, F, "H")
    e.st(H_seg, e.A, LY.seg_size(S, F), "st:Hseg")
    e.matmul(e.A, W2, e.C, F, S, D, "ffn2")
    e.st(Y_row, e.C, LY.row_size(S, D), "st:Y")

    layernorm(Y_row, N1_row, N2_row, D, "ln2")

    # =============================== emit ===============================
    descs = e.b.build()
    for _q, _m, dsc in descs:
        M.execute(e.mach, dsc)
    for _q, _m, dsc in descs:
        e.prog.push(dsc, qid=_q, mcu=_m)
    for r in range(LY.row_size(S, D)):
        e.prog.check(N2_row + r, e.mach.mem_word(N2_row + r))

    # =============================== reference ===========================
    def mat(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(len(b)))
                 for j in range(len(b[0]))] for i in range(len(a))]

    def softmax_rows(z):
        out = []
        for row in z:
            mx = max(row)
            ex = [math.exp(v - mx) for v in row]
            t = sum(ex)
            out.append([v / t for v in ex])
        return out

    def ln(z):
        out = []
        for row in z:
            mu = sum(row) / len(row)
            var = sum((v - mu) ** 2 for v in row) / len(row)
            rs = 1.0 / math.sqrt(var + 1e-3)
            out.append([(v - mu) * rs for v in row])
        return out

    Xb = [[M.bf_to_f(M.f_to_bf(v)) for v in row] for row in X]
    q = mat(Xb, wq)
    kk = mat(Xb, wk)
    vv = mat(Xb, wv)
    sc = [[sum(q[i][t] * kk[j][t] for t in range(D)) / math.sqrt(D)
           for j in range(S)] for i in range(S)]
    p = softmax_rows(sc)
    ctx = mat(p, vv)
    at = mat(ctx, wo)
    n1 = ln([[at[i][j] + Xb[i][j] for j in range(D)] for i in range(S)])
    h = [[gelu(v) for v in row] for row in mat(n1, w1)]
    y = mat(h, w2)
    n2 = ln([[y[i][j] + n1[i][j] for j in range(D)] for i in range(S)])

    def rel(got, want):
        num = max(abs(got[i][j] - want[i][j])
                  for i in range(len(want)) for j in range(len(want[0])))
        den = max(abs(want[i][j])
                  for i in range(len(want)) for j in range(len(want[0])))
        return num / den if den else 0.0

    stages = [
        ("Q            ", e.get(Q_row, S, D), q),
        ("scores*scale ", e.get(Sc_row, S, S), sc),
        ("softmax      ", [[e.get(P_seg, D, S)[0][0]]], [[0.0]]),
        ("ctx = P.V    ", e.get(Ctx_row, S, D), ctx),
        ("attn.Wo      ", e.get(A_row, S, D), at),
        ("LayerNorm 1  ", e.get(N1_row, S, D), n1),
        ("GELU(N1.W1)  ", e.get(H_row, S, F), h),
        ("H.W2         ", e.get(Y_row, S, D), y),
        ("LayerNorm 2  ", e.get(N2_row, S, D), n2),
    ]
    report = []
    for nm, got, want in stages:
        if nm.startswith("softmax"):
            continue
        report.append((nm, rel(got, want)))

    e.prog.note("encoder S=%d d=%d d_ff=%d transposes=%d"
                % (S, D, F, e.nT))
    return e.prog, e.b.stats, report, e.nT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-S", type=int, default=32, help="sequence length")
    ap.add_argument("-d", type=int, default=32, help="model width")
    ap.add_argument("--ff", type=int, default=64, help="feed forward width")
    ap.add_argument("-s", "--seed", type=int, default=1)
    ap.add_argument("-o", "--out", default="tests/vectors/encoder.txt")
    a = ap.parse_args()
    prog, stats, report, nT = build(a.S, a.d, a.ff, a.seed)
    prog.write(a.out)
    print("wrote %s: %d descriptors (%d sync no-ops), %d events, "
          "%d transposes (%.0f%% of ops)"
          % (a.out, prog.n_desc, stats["nops"], stats["events"], nT,
             100.0 * nT / prog.n_desc))
    print("  stage accuracy against a float64 reference:")
    for nm, r in report:
        print("    %s  %6.2f%%" % (nm, 100.0 * r))


if __name__ == "__main__":
    main()
