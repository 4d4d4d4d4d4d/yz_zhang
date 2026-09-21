"""Functional model of the NPU, bit-exact against the RTL.

Used by the code generators to compute the expected results that go into a
program's check lines, so every generated kernel is self-checking.

Arithmetic notes
  * fixed point is plain Python integer arithmetic with the same
    round-half-away-from-zero shift and saturation as npu_fp::shift_sat
  * bf16 multiply is exact, so computing it in a Python double and rounding
    once to float32 is the same value the RTL produces
  * fp32 add is computed in a double and rounded once to float32; this is
    correctly rounded except in double-rounding corner cases that need an
    exponent spread wider than 53 bits, which no generated kernel produces
  * subnormals are flushed to zero on every result, matching the declared
    FTZ semantics
"""
import struct
from npu_isa import (LANES, BUS_W, NBUF, BUF_D, BUF_AW, BEAT_B, P_CUBE, P_VEC,
                     P_FIX, P_MTE_IN, P_MTE_OUT, OPC_NOP, C_MM, F_TRANS,
                     M_XFER, V_MOV, V_ADDI, V_MULI, V_MAXI, V_ADD, V_SUB,
                     V_MUL, V_MAX, V_MIN, V_BRC_R, V_BRC_C, V_RED_SUM,
                     V_RED_MAX, V_LUT, V_RECIP, V_SEL, V_SELD, V_CVT_F2I,
                     V_CVT_I2F, SUB_ADD, SUB_SUB, SUB_MUL, SUB_MAX)

MIN_NORM32 = 2.0 ** -126


# ============================== arithmetic ==============================
def f32(x):
    """Round a Python float to the nearest float32, flushing subnormals."""
    try:
        y = struct.unpack(">f", struct.pack(">f", x))[0]
    except OverflowError:
        return float("inf") if x > 0 else float("-inf")
    if y != y or y in (float("inf"), float("-inf")):
        return y
    if y != 0.0 and abs(y) < MIN_NORM32:
        return 0.0 if y > 0 else -0.0
    return y


def bf_to_f(b):
    b &= 0xFFFF
    if (b >> 7) & 0xFF == 0:                      # zero or subnormal -> FTZ
        return -0.0 if b >> 15 else 0.0
    return struct.unpack(">f", struct.pack(">I", b << 16))[0]


def f_to_bf(x):
    """float -> bf16, round to nearest even, FTZ, canonical quiet NaN."""
    if x != x:
        return 0x7FC0
    try:
        bits = struct.unpack(">I", struct.pack(">f", x))[0]
    except OverflowError:
        return 0xFF80 if x < 0 else 0x7F80
    e, m = (bits >> 23) & 0xFF, bits & 0x7FFFFF
    if e == 0xFF:
        return (bits >> 16) & 0xFFFF if m == 0 else 0x7FC0
    if e == 0:
        return (bits >> 31) << 15
    rnd = ((bits >> 15) & 1) and ((bits & 0x7FFF) != 0 or ((bits >> 16) & 1))
    top = (bits >> 16) + (1 if rnd else 0)
    return top & 0xFFFF


def bf_mul(a, b):
    """bf16 x bf16 -> float32 value, exact (no rounding in the multiplier)."""
    ea, eb = (a >> 7) & 0xFF, (b >> 7) & 0xFF
    s = ((a >> 15) ^ (b >> 15)) & 1
    if ea == 0xFF or eb == 0xFF:
        if (ea == 0xFF and (a & 0x7F)) or (eb == 0xFF and (b & 0x7F)):
            return float("nan")
        if (ea == 0xFF and eb == 0) or (eb == 0xFF and ea == 0):
            return float("nan")
        return float("-inf") if s else float("inf")
    if ea == 0 or eb == 0:
        return -0.0 if s else 0.0
    return f32(bf_to_f(a) * bf_to_f(b))


def bf_gt(a, b):
    ka = (~a & 0xFFFF) if (a >> 15) else (a | 0x8000)
    kb = (~b & 0xFFFF) if (b >> 15) else (b | 0x8000)
    return ka > kb


def bf_recip(a):
    e = (a >> 7) & 0xFF
    if e == 0:
        return (a & 0x8000) | 0x7F80
    if e == 0xFF:
        return 0x7FC0 if (a & 0x7F) else (a & 0x8000)
    m = ((1 << 15) | ((a & 0x7F) << 8))          # Q16 in [0.5,1)
    r = 185044 - ((123363 * m) >> 16)
    for _ in range(3):
        t = (1 << 33) - m * r
        r = (r * t) >> 32
    eo = 253 - e
    if r >= (1 << 17):
        r >>= 1
        eo += 1
    if eo <= 0:
        return a & 0x8000
    if eo >= 255:
        return (a & 0x8000) | 0x7F80
    return f_to_bf_bits((a >> 15) & 1, eo, (r & 0xFFFF) << 7)


def f_to_bf_bits(sign, exp, frac23):
    return f_to_bf(struct.unpack(">f", struct.pack(
        ">I", (sign << 31) | (exp << 23) | (frac23 & 0x7FFFFF)))[0])


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def sat16(v):
    if v > 32767:
        return 0x7FFF
    if v < -32768:
        return 0x8000
    return v & 0xFFFF


def shift_sat(v, sh):
    if sh == 0:
        return sat16(v)
    return sat16((v + (1 << (sh - 1))) >> sh)


def f_to_int(x, sh):
    """Round toward zero of x * 2^sh, saturated to int32.

    NaN converts to zero and infinity saturates, matching npu_fp::fp32_to_int.
    """
    if x != x:
        return 0
    if x in (float("inf"), float("-inf")):
        return 2147483647 if x > 0 else -2147483648
    y = int(x * (2.0 ** sh))                      # Python int() truncates
    return max(-2147483648, min(2147483647, y))


def int_to_f(v, sh):
    return f32(v / (2.0 ** sh))


# ============================== state ==============================
class Machine:
    def __init__(self, mem_beats=65536):
        # buffers: [buf][beat][lane] of uint16
        self.buf = [[[0] * LANES for _ in range(BUF_D)] for _ in range(NBUF)]
        self.mem = {}                             # beat index -> [uint16]*16
        self.acc = [[0] * LANES for _ in range(LANES)]   # CUBE accumulator
        self.mem_beats = mem_beats

    # ---- external memory ----
    def mem_get(self, beat):
        return list(self.mem.get(beat, [0] * LANES))

    def mem_set(self, beat, lanes):
        self.mem[beat] = list(lanes)

    def mem_word(self, beat):
        w = 0
        for l in reversed(self.mem_get(beat)):
            w = (w << 16) | (l & 0xFFFF)
        return w

    def mem_set_word(self, beat, word):
        self.mem_set(beat, [(word >> (16 * l)) & 0xFFFF for l in range(LANES)])

    # ---- buffers ----
    def _split(self, a):
        return (a >> BUF_AW) & (NBUF - 1), a & (BUF_D - 1)

    def bget(self, a):
        b, o = self._split(a)
        return list(self.buf[b][o])

    def bput(self, a, lanes, mask=0xFFFF):
        b, o = self._split(a)
        for l in range(LANES):
            if mask & (1 << l):
                self.buf[b][o][l] = lanes[l] & 0xFFFF


# ============================== decode ==============================
def bits(v, hi, lo):
    return (v >> lo) & ((1 << (hi - lo + 1)) - 1)


def decode(d):
    h = d & 0xFFFFFFFF
    return {
        "vld": bits(h, 0, 0), "pipe": bits(h, 3, 1), "opc": bits(h, 9, 4),
        "tag": bits(h, 17, 10), "set_en": bits(h, 18, 18),
        "set_evt": bits(h, 22, 19), "bar_q": bits(h, 23, 23),
        "bar_g": bits(h, 24, 24), "fp": bits(h, 25, 25),
        "wait": bits(d, 47, 32), "pl": bits(d, 255, 64),
    }


def d_cube(p):
    return {"src_a": bits(p, 15, 0), "src_b": bits(p, 31, 16),
            "dst": bits(p, 47, 32), "rows": bits(p, 67, 64) + 1,
            "n_dim": bits(p, 71, 68) + 1, "acc_cont": bits(p, 72, 72),
            "acc_hold": bits(p, 73, 73), "relu": bits(p, 74, 74),
            "shift": bits(p, 79, 75), "k_len": bits(p, 95, 80),
            "a_stride": bits(p, 111, 96), "b_stride": bits(p, 127, 112),
            "c_stride": bits(p, 143, 128)}


def d_vec(p):
    return {"src_a": bits(p, 15, 0), "src_b": bits(p, 31, 16),
            "dst": bits(p, 47, 32), "rows": bits(p, 63, 48),
            "mask": bits(p, 79, 64), "a_stride": bits(p, 95, 80),
            "b_stride": bits(p, 111, 96), "d_stride": bits(p, 127, 112),
            "imm": bits(p, 159, 128), "subop": bits(p, 161, 160)}


def d_fix(p):
    return {"src_a": bits(p, 15, 0), "s_stride": bits(p, 31, 16),
            "dst": bits(p, 47, 32), "tiles": bits(p, 63, 48),
            "d_stride": bits(p, 79, 64)}


def d_mte(p):
    return {"ext_addr": bits(p, 47, 0), "buf_addr": bits(p, 63, 48),
            "buf_rstride": bits(p, 79, 64), "cols": bits(p, 95, 80),
            "rows": bits(p, 111, 96), "ext_rstride": bits(p, 143, 112),
            "in_cnt": bits(p, 159, 144), "in_stride": bits(p, 175, 160)}


# ============================== execution ==============================
def agu(c):
    """Yield (external beat, on-chip beat) in the order the AGU walks them."""
    icnt = c["cols"] if c["in_cnt"] == 0 else c["in_cnt"]
    istr = c["cols"] if c["in_cnt"] == 0 else c["in_stride"]
    base = c["ext_addr"] // BEAT_B
    for r in range(c["rows"]):
        for col in range(c["cols"]):
            g, w = divmod(col, icnt)
            yield (base + r * c["ext_rstride"] + g * istr + w,
                   c["buf_addr"] + r * c["buf_rstride"] + col)


def _bin(sub, fp, a, b, sh):
    if fp:
        if sub == SUB_ADD:
            return f_to_bf(f32(bf_to_f(a) + bf_to_f(b)))
        if sub == SUB_SUB:
            return f_to_bf(f32(bf_to_f(a) - bf_to_f(b)))
        if sub == SUB_MUL:
            return f_to_bf(bf_mul(a, b))
        return a if bf_gt(a, b) else b
    x, y = s16(a), s16(b)
    if sub == SUB_ADD:
        return sat16(x + y)
    if sub == SUB_SUB:
        return sat16(x - y)
    if sub == SUB_MUL:
        return shift_sat(x * y, sh)
    return a if x > y else b


def _lut_idx(fp, a, imm):
    lo, sh = imm & 0xFFFF, (imm >> 16) & 0x1F
    if fp:
        t = f_to_int(f32(bf_to_f(a) - bf_to_f(lo)), sh)
    else:
        t = (s16(a) - s16(lo)) >> sh
    return max(0, min(15, t))


def exec_vec(M, d, c):
    fp, opc, rows = d["fp"], d["opc"], c["rows"]
    mask, imm = c["mask"], c["imm"]
    sh = (imm >> 16) & 0x1F
    red = opc in (V_RED_SUM, V_RED_MAX)
    kreg = [None, None]

    if opc in (V_BRC_R,):
        kreg[0] = M.bget(c["src_b"])
    elif opc == V_LUT:
        kreg[0] = M.bget(c["src_b"])
        kreg[1] = M.bget(c["src_b"] + c["b_stride"])

    pack, pack_mask = [0] * LANES, 0
    for r in range(rows):
        a = M.bget(c["src_a"] + r * c["a_stride"])

        if opc in (V_ADD, V_SUB, V_MUL, V_MAX, V_MIN, V_SELD):
            b = M.bget(c["src_b"] + r * c["b_stride"])
        elif opc == V_BRC_R:
            b = kreg[0]
        elif opc == V_BRC_C:
            beat = M.bget(c["src_b"] + (r // LANES) * c["b_stride"])
            b = [beat[r % LANES]] * LANES
        else:
            b = [0] * LANES

        if red:
            if opc == V_RED_SUM:
                if fp:
                    acc = 0.0
                    for l in range(LANES):
                        if mask & (1 << l):
                            acc = f32(acc + bf_to_f(a[l]))
                    v = f_to_bf(acc)
                else:
                    acc = sum(s16(a[l]) for l in range(LANES)
                              if mask & (1 << l))
                    v = shift_sat(acc, sh)
            else:
                v, first = 0, True
                for l in range(LANES):
                    if mask & (1 << l):
                        if first:
                            v, first = a[l], False
                        elif (bf_gt(a[l], v) if fp else s16(a[l]) > s16(v)):
                            v = a[l]
            pack[r % LANES] = v
            pack_mask |= 1 << (r % LANES)
            if (r % LANES) == LANES - 1 or r == rows - 1:
                M.bput(c["dst"] + (r // LANES) * c["d_stride"], pack, pack_mask)
                pack, pack_mask = [0] * LANES, 0
            continue

        out = [0] * LANES
        for l in range(LANES):
            av, bv = a[l], b[l]
            if opc in (V_MOV, V_SEL, V_SELD):
                y = av
            elif opc == V_ADDI:
                y = _bin(SUB_ADD, fp, av, imm & 0xFFFF, sh)
            elif opc == V_MULI:
                y = _bin(SUB_MUL, fp, av, imm & 0xFFFF, sh)
            elif opc == V_MAXI:
                y = _bin(SUB_MAX, fp, av, imm & 0xFFFF, sh)
            elif opc == V_ADD:
                y = _bin(SUB_ADD, fp, av, bv, sh)
            elif opc == V_SUB:
                y = _bin(SUB_SUB, fp, av, bv, sh)
            elif opc == V_MUL:
                y = _bin(SUB_MUL, fp, av, bv, sh)
            elif opc == V_MAX:
                y = _bin(SUB_MAX, fp, av, bv, sh)
            elif opc == V_MIN:
                y = bv if _bin(SUB_MAX, fp, av, bv, sh) == av else av
            elif opc in (V_BRC_R, V_BRC_C):
                y = _bin(c["subop"], fp, av, bv, sh)
            elif opc == V_RECIP:
                y = bf_recip(av)
            elif opc == V_CVT_F2I:
                y = sat16(f_to_int(bf_to_f(av), sh))
            elif opc == V_CVT_I2F:
                y = f_to_bf(int_to_f(s16(av), sh))
            elif opc == V_LUT:
                ix = _lut_idx(fp, av, imm)
                y = _bin(SUB_ADD, fp,
                         _bin(SUB_MUL, fp, av, kreg[0][ix], (imm >> 21) & 0x1F),
                         kreg[1][ix], 0)
            else:
                y = av
            out[l] = y

        pred = mask
        if opc == V_SELD:
            pred = 0
            for l in range(LANES):
                if not (mask & (1 << l)):
                    continue
                bb = b[l]
                ok = (not (bb >> 15) and (bb & 0x7FFF)) if fp else s16(bb) > 0
                if ok:
                    pred |= 1 << l
        M.bput(c["dst"] + r * c["d_stride"], out, pred)


def execute(M, d_word):
    """Run one descriptor against the machine state."""
    d = decode(d_word)
    if d["opc"] == OPC_NOP:
        return
    p = d["pipe"]

    if p == P_CUBE:
        c = d_cube(d["pl"])
        if not c["acc_cont"]:
            M.acc = [[0] * LANES for _ in range(LANES)]
        for k in range(c["k_len"]):
            a = M.bget(c["src_a"] + k * c["a_stride"])
            b = M.bget(c["src_b"] + k * c["b_stride"])
            for i in range(c["rows"]):
                for j in range(c["n_dim"]):
                    if d["fp"]:
                        M.acc[i][j] = f32(M.acc[i][j] + bf_mul(a[i], b[j]))
                    else:
                        M.acc[i][j] += s16(a[i]) * s16(b[j])
        if not c["acc_hold"]:
            wmask = (1 << c["n_dim"]) - 1
            for i in range(c["rows"]):
                row = [0] * LANES
                for j in range(c["n_dim"]):
                    v = M.acc[i][j]
                    w = f_to_bf(v) if d["fp"] else shift_sat(v, c["shift"])
                    if c["relu"] and (w >> 15):
                        w = 0
                    row[j] = w
                M.bput(c["dst"] + i * c["c_stride"], row, wmask)

    elif p == P_VEC:
        exec_vec(M, d, d_vec(d["pl"]))

    elif p == P_FIX:
        c = d_fix(d["pl"])
        for t in range(c["tiles"]):
            src = [M.bget(c["src_a"] + t * c["s_stride"] + r)
                   for r in range(LANES)]
            for r in range(LANES):
                M.bput(c["dst"] + t * c["d_stride"] + r,
                       [src[l][r] for l in range(LANES)])

    elif p == P_MTE_IN:
        for e, b in agu(d_mte(d["pl"])):
            M.bput(b, M.mem_get(e))

    elif p == P_MTE_OUT:
        for e, b in agu(d_mte(d["pl"])):
            M.mem_set(e, M.bget(b))

    else:
        raise ValueError(f"illegal pipe {p}")


def run(M, descs):
    """Execute a program in order. A well-formed program's event graph makes
    every legal issue order produce this same result."""
    for d in descs:
        execute(M, d)
