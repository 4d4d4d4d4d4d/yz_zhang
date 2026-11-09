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
    """母题识别。两种信号，都要求“时间爆发”：

    1. 标签爆发：一个**新出现**的标签在窗口内被 >= burst 个不同作者使用（例如 #脚开瓶盖挑战）。
       标签首次出现早于窗口（老标签 = 常态品类，如 #做菜）则不形成母题。
    2. 文本相似爆发：宽松文本相似（距离 <= bits）的内容在窗口内来自 >= burst 个不同作者。
       注意：真正改写过的文案彼此距离通常接近随机（约 32），文本信号只能抓到“模板文案”。

    已存在的母题优先吸收新成员；开创者 = 母题成员中日志顺序最早者。
    """

    def __init__(self, bits: int = MOTIF_BITS, burst: int = 5, window_s: int = 7 * 86_400) -> None:
        self.bits = bits
        self.burst = burst
        self.window_s = window_s
        self.index = MultiIndex()
        self.meta: dict[str, tuple[str, int]] = {}  # cid -> (author, ts)
        self.order: dict[str, int] = {}
        self.motif_of: dict[str, str] = {}
        self.motifs: dict[str, Motif] = {}
        self.tag_first: dict[str, int] = {}
        self.tag_members: dict[str, list[str]] = {}
        self.tag_motif: dict[str, str] = {}

    def _create(self, members: list[str], tag: str = "") -> str:
        members = sorted({c for c in members if c not in self.motif_of}, key=self.order.__getitem__)
        m = Motif(members[0], members)
        self.motifs[m.motif_id] = m
        for c in members:
            self.motif_of[c] = m.motif_id
        if tag:
            self.tag_motif[tag] = m.motif_id
        return m.motif_id

    def _authors(self, cids: list[str]) -> int:
        return len({self.meta[c][0] for c in cids})

    def add(
        self, cid: str, author: str, fp: int | None, ts: int, tags: tuple[str, ...] = ()
    ) -> str:
        """加入一条内容，返回其所属母题 ID（无则空串）。"""
        similar: list[str] = []
        if fp is not None:
            similar = [c for c in self.index.query(fp, self.bits) if c in self.meta]
            self.index.add(cid, fp)
        self.meta[cid] = (author, ts)
        self.order[cid] = len(self.order)
        for tag in tags:
            self.tag_first.setdefault(tag, ts)
            self.tag_members.setdefault(tag, []).append(cid)
        joined = {self.motif_of[c] for c in similar if c in self.motif_of}
        joined |= {self.tag_motif[t] for t in tags if t in self.tag_motif}
        if joined:
            mid = min(joined, key=self.order.__getitem__)
            self.motifs[mid].members.append(cid)
            self.motif_of[cid] = mid
            return mid
        group = [c for c in similar if ts - self.meta[c][1] <= self.window_s] + [cid]
        if self._authors(group) >= self.burst:
            return self._create(group)
        for tag in sorted(tags):
            if ts - self.tag_first[tag] > self.window_s:
                continue  # 老标签：常态品类
            members = [c for c in self.tag_members[tag] if ts - self.meta[c][1] <= self.window_s]
            if self._authors(members) >= self.burst:
                return self._create(members, tag)
        return ""
