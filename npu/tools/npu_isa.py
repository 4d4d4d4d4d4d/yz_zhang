"""Descriptor encoding for the NPU.

Field positions here are the contract with rtl/npu_pkg.sv. If a struct in
the package changes, this file changes with it -- tests/test_isa.py checks
a handful of encodings against values dumped by the RTL testbench.
"""

# ---------------- geometry (mirrors npu_pkg) ----------------
LANES, ELEM_W, BUS_W = 16, 16, 256
NBUF, BUF_D, BUF_AW, BUFIDW = 4, 256, 8, 2
BEAT_B = BUS_W // 8
NQ, NMCU, NPIPE, NEVT = 8, 4, 5, 16
WIN, CREDIT, MAX_BURST = 8, 4, 16

# ---------------- pipes ----------------
P_CUBE, P_VEC, P_FIX, P_MTE_IN, P_MTE_OUT = 0, 1, 2, 3, 4

OPC_NOP = 0x3F
C_MM = 0
F_TRANS = 0
M_XFER = 0

(V_MOV, V_ADDI, V_MULI, V_MAXI, V_ADD, V_SUB, V_MUL, V_MAX, V_MIN,
 V_BRC_R, V_BRC_C, V_RED_SUM, V_RED_MAX, V_LUT, V_RECIP, V_SEL, V_SELD,
 V_CVT_F2I, V_CVT_I2F) = range(19)

SUB_ADD, SUB_SUB, SUB_MUL, SUB_MAX = 0, 1, 2, 3

VEC_NAMES = {
    V_MOV: "mov", V_ADDI: "addi", V_MULI: "muli", V_MAXI: "maxi",
    V_ADD: "add", V_SUB: "sub", V_MUL: "mul", V_MAX: "max", V_MIN: "min",
    V_BRC_R: "brc_r", V_BRC_C: "brc_c", V_RED_SUM: "red_sum",
    V_RED_MAX: "red_max", V_LUT: "lut", V_RECIP: "recip", V_SEL: "sel",
    V_SELD: "seld", V_CVT_F2I: "cvt_f2i", V_CVT_I2F: "cvt_i2f",
    OPC_NOP: "nop",
}
PIPE_NAMES = ["CUBE", "VEC", "FIX", "MTE_IN", "MTE_OUT"]


def addr(buf, beat):
    """On-chip address: {buf[1:0], beat[7:0]} in the low 10 bits."""
    assert 0 <= buf < NBUF, buf
    assert 0 <= beat < BUF_D, beat
    return (buf << BUF_AW) | beat


def _pack(fields, total):
    """fields: list of (width, value) written most significant first."""
    v, used = 0, 0
    for w, x in fields:
        assert 0 <= x < (1 << w), f"field {x} does not fit in {w} bits"
        v = (v << w) | x
        used += w
    assert used == total, f"packed {used} bits, expected {total}"
    return v


def header(pipe, opc, tag=0, set_evt=0, set_en=0, bar_q=0, bar_g=0, fp=0):
    return _pack([(6, 0), (1, fp), (1, bar_g), (1, bar_q), (4, set_evt),
                  (1, set_en), (8, tag), (6, opc), (3, pipe), (1, 1)], 32)


def desc(pipe, opc, payload, wait_mask=0, **kw):
    """Assemble a 256-bit descriptor."""
    assert payload < (1 << 192)
    return (payload << 64) | ((wait_mask & 0xFFFF) << 32) | header(pipe, opc, **kw)


# ---------------- payloads ----------------
def cube_pl(src_a, src_b, dst, k_len, rows=16, n_dim=16, a_stride=1,
            b_stride=1, c_stride=1, shift=0, relu=0, acc_cont=0, acc_hold=0):
    return _pack([(48, 0), (16, c_stride), (16, b_stride), (16, a_stride),
                  (16, k_len), (5, shift), (1, relu), (1, acc_hold),
                  (1, acc_cont), (4, n_dim - 1), (4, rows - 1), (16, 0),
                  (16, dst), (16, src_b), (16, src_a)], 192)


def vec_pl(src_a, dst, rows, src_b=0, mask=0xFFFF, a_stride=1, b_stride=1,
           d_stride=1, imm=0, subop=SUB_ADD):
    return _pack([(30, 0), (2, subop), (32, imm & 0xFFFFFFFF),
                  (16, d_stride), (16, b_stride), (16, a_stride),
                  (16, mask), (16, rows), (16, dst), (16, src_b),
                  (16, src_a)], 192)


def fix_pl(src_a, dst, tiles, s_stride=LANES, d_stride=LANES):
    return _pack([(112, 0), (16, d_stride), (16, tiles), (16, dst),
                  (16, s_stride), (16, src_a)], 192)


def mte_pl(ext_addr, buf_addr, rows, cols, ext_rstride=None, buf_rstride=None,
           in_cnt=0, in_stride=0):
    if ext_rstride is None:
        ext_rstride = cols
    if buf_rstride is None:
        buf_rstride = cols
    assert ext_addr % BEAT_B == 0, "external address must be beat aligned"
    return _pack([(16, 0), (16, in_stride), (16, in_cnt), (32, ext_rstride),
                  (16, rows), (16, cols), (16, buf_rstride), (16, buf_addr),
                  (48, ext_addr)], 192)


# ---------------- convenience builders ----------------
def mm(src_a, src_b, dst, k, **kw):
    hdr = {k_: kw.pop(k_) for k_ in
           ("tag", "set_evt", "set_en", "bar_q", "bar_g", "fp", "wait_mask")
           if k_ in kw}
    wm = hdr.pop("wait_mask", 0)
    return desc(P_CUBE, C_MM, cube_pl(src_a, src_b, dst, k, **kw),
                wait_mask=wm, **hdr)


def vop(opc, src_a, dst, rows, **kw):
    hdr = {k_: kw.pop(k_) for k_ in
           ("tag", "set_evt", "set_en", "bar_q", "bar_g", "fp", "wait_mask")
           if k_ in kw}
    wm = hdr.pop("wait_mask", 0)
    return desc(P_VEC, opc, vec_pl(src_a, dst, rows, **kw),
                wait_mask=wm, **hdr)


def trans(src_a, dst, tiles, **kw):
    hdr = {k_: kw.pop(k_) for k_ in
           ("tag", "set_evt", "set_en", "bar_q", "bar_g", "fp", "wait_mask")
           if k_ in kw}
    wm = hdr.pop("wait_mask", 0)
    return desc(P_FIX, F_TRANS, fix_pl(src_a, dst, tiles, **kw),
                wait_mask=wm, **hdr)


def dma(pipe, ext_addr, buf_addr, rows, cols, **kw):
    hdr = {k_: kw.pop(k_) for k_ in
           ("tag", "set_evt", "set_en", "bar_q", "bar_g", "fp", "wait_mask")
           if k_ in kw}
    wm = hdr.pop("wait_mask", 0)
    return desc(pipe, M_XFER, mte_pl(ext_addr, buf_addr, rows, cols, **kw),
                wait_mask=wm, **hdr)


def nop(pipe, **kw):
    hdr = {k_: kw.pop(k_) for k_ in
           ("tag", "set_evt", "set_en", "bar_q", "bar_g", "fp", "wait_mask")
           if k_ in kw}
    wm = hdr.pop("wait_mask", 0)
    return desc(pipe, OPC_NOP, 0, wait_mask=wm, **hdr)


# ---------------- program file ----------------
class Program:
    """Collects descriptors and checks into the tb_npu_prog text format."""

    def __init__(self):
        self.lines = []
        self.n_desc = 0

    def note(self, s):
        self.lines.append(f"N {s}")

    def comment(self, s):
        self.lines.append(f"# {s}")

    def mem(self, beat, value256):
        self.lines.append(f"M {beat:x} {value256:064x}")

    def push(self, d, qid=0, mcu=0):
        self.lines.append(f"D {qid:x} {mcu:x} {d:064x}")
        self.n_desc += 1

    def check(self, beat, value256, mask=None):
        if mask is None:
            self.lines.append(f"C {beat:x} {value256:064x}")
        else:
            self.lines.append(f"X {beat:x} {value256:064x} {mask:064x}")

    def check_csr(self, off, value):
        self.lines.append(f"S {off:x} {value:08x}")

    def write(self, path):
        with open(path, "w") as f:
            f.write("\n".join(self.lines) + "\n")
        return path
