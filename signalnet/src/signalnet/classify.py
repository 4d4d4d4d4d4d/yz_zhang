"""四分类与范式（母题）识别（L2 层）。

分类：搬运 copy / 衍生 derivative / 追随 follower / 原创 original（REQ-MT-001）。
- 机器只给“预判”（prior）：近重复 → copy；声明衍生 → derivative；落入母题 → follower。
- 陪审按质押加权多数裁定；平票时按判定顺序 copy > derivative > follower > original。
- 声明了衍生关系的内容不判为搬运：copy 票计为 derivative（REQ-OR-003）。

母题（REQ-MT-002）：宽松文本相似（汉明距离 <= MOTIF_BITS）+ 时间爆发（窗口内 >= burst 个
不同作者）→ 生成母题；开创者为簇内日志顺序最早者。常态品类文本彼此不相似，不会形成母题。

相关需求：REQ-MT-001, REQ-MT-002, REQ-MT-005, REQ-OR-002
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .attestation import CLASSES
from .fingerprint import MultiIndex

MOTIF_BITS = 20
COPY_CAP = 0.29  # 被判为搬运时共识分封顶（原创性一票否决，REQ-OR-002）


def classify(votes: list[tuple[str, float]], prior: str, declared_derivative: bool) -> str:
    tally: dict[str, float] = {}
    for klass, w in votes:
        if not klass:
            continue
        if klass == "copy" and declared_derivative:
            klass = "derivative"
        tally[klass] = tally.get(klass, 0.0) + w
    if not tally:
        return prior
    best = max(tally.values())
    for klass in CLASSES:  # 判定顺序决定平票
        if tally.get(klass, 0.0) == best:
            return klass
    return prior


@dataclass
class Motif:
    motif_id: str  # = 开创者内容 ID
    members: list[str] = field(default_factory=list)  # 日志顺序，含开创者

    def ordinal(self, cid: str) -> int:
        """追随序号：开创者为 1，其后依次 2,3,...（探索配额按 1/n，REQ-MT-005）。"""
        return self.members.index(cid) + 1


class MotifIndex:
    def __init__(self, bits: int = MOTIF_BITS, burst: int = 5, window_s: int = 7 * 86_400) -> None:
        self.bits = bits
        self.burst = burst
        self.window_s = window_s
        self.index = MultiIndex()
        self.meta: dict[str, tuple[str, int]] = {}  # cid -> (author, ts)
        self.motif_of: dict[str, str] = {}
        self.motifs: dict[str, Motif] = {}

    def add(self, cid: str, author: str, fp: int, ts: int) -> str:
        """加入一条内容，返回其所属母题 ID（无则空串）。"""
        similar = [c for c in self.index.query(fp, self.bits) if c in self.meta]
        self.index.add(cid, fp)
        self.meta[cid] = (author, ts)
        joined = sorted({self.motif_of[c] for c in similar if c in self.motif_of})
        if joined:
            m = self.motifs[joined[0]]
            m.members.append(cid)
            self.motif_of[cid] = m.motif_id
            return m.motif_id
        group = [c for c in similar if ts - self.meta[c][1] <= self.window_s] + [cid]
        authors = {self.meta[c][0] for c in group}
        if len(authors) < self.burst:
            return ""
        m = Motif(group[0], list(group))
        self.motifs[m.motif_id] = m
        for c in group:
            self.motif_of[c] = m.motif_id
        return m.motif_id
