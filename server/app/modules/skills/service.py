"""SKL-100 技能的语义匹配（135 号 spec）。

「VI 设计」「标志设计」「logo 设计」说的是同一件事：按**技能概念表**归到同一个规范名（「品牌设计」）再比。
概念表 = 仓库种子 + 运营在后台的增改（后台优先；下线的概念整组不生效）。
概念表认不出的就当不同——如实不猜（向量相似兜底见 SKL-110）。
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

SEED = Path(__file__).resolve().parent / "seeds" / "concepts.json"


def norm(s: str) -> str:
    """全角转半角、去空格与常见符号、英文小写：「VI 设计」「ＶＩ设计」「vi设计」都是同一个键。"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s\-_·/、]+", "", s)


@lru_cache(maxsize=1)
def _seed() -> tuple[tuple[str, tuple[str, ...]], ...]:
    data = json.loads(SEED.read_text(encoding="utf-8"))
    return tuple((c["name"], tuple(c.get("aliases") or [])) for c in data["concepts"])


def concepts(db: Session | None = None) -> list[dict]:
    """生效的概念：种子 + 后台增改（同名以后台为准；后台下线的不生效）。"""
    out = {name: list(aliases) for name, aliases in _seed()}
    if db is not None:
        from .models import SkillConcept

        for c in db.query(SkillConcept).all():
            if c.status == "retired":
                out.pop(c.name, None)
            else:
                out[c.name] = list(c.aliases or [])
    return [{"name": n, "aliases": a} for n, a in sorted(out.items())]


def index(db: Session | None = None) -> dict[str, str]:
    """归一化后的词 → 规范名。"""
    idx: dict[str, str] = {}
    for c in concepts(db):
        idx[norm(c["name"])] = c["name"]
        for a in c["aliases"]:
            idx.setdefault(norm(a), c["name"])
    return idx


def canonical(skill: str, idx: dict[str, str]) -> str:
    """认得出就给规范名，认不出就原样（归一化前的写法）返回。"""
    return idx.get(norm(skill), skill)


def matcher(db: Session | None):
    """返回 same(a, b)：归一化后相同，或属于同一个概念。

    向量相似兜底（SKL-110）这一批不做：撮合在请求事务里，按 CONC-067 不能挂着事务调外部模型；
    要做得先离线算好技能词的向量，见 135 号「没做的」。
    """
    idx = index(db)

    def same(a: str, b: str) -> bool:
        return norm(a) == norm(b) or canonical(a, idx) == canonical(b, idx)

    return same


def aliases_in(text: str, db: Session | None = None) -> dict[str, str]:
    """文本里出现了哪些概念的写法：{写法: 规范名}。长的写法优先，被包含的短写法不重复算。"""
    low = norm(text)
    found: dict[str, str] = {}
    pairs = sorted(((w, c["name"]) for c in concepts(db) for w in [c["name"], *c["aliases"]]), key=lambda x: -len(norm(x[0])))
    taken: list[str] = []
    for w, name in pairs:
        k = norm(w)
        if len(k) >= 2 and k in low and not any(k in t for t in taken):
            found[w] = name
            taken.append(k)
    return found


def expand_query(q: str, db: Session | None = None) -> str:
    """KB-110 检索时把问题里的概念换成「规范名 + 全部别名」：问「VI 设计」也找得到写着「品牌设计」的笔记。"""
    extra: list[str] = []
    cs = {c["name"]: c["aliases"] for c in concepts(db)}
    for name in dict.fromkeys(aliases_in(q, db).values()):
        extra += [name, *cs.get(name, [])]
    return q if not extra else f"{q} {' '.join(dict.fromkeys(extra))}"
