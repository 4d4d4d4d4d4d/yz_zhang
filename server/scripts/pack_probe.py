"""PACK-091（396 号 spec）场景包问法离线试分：写测试之前先看这些问法答不答得上、是不是真的只靠标签。

    python -m scripts.pack_probe pet-boarding "要看疫苗本吗=>vaccine-and-health-check" "!猫瘟=>vaccine-and-health-check"

- 每一项写成「问题=>知识 key」；知识也可以写 key 或标题的开头几个字（能唯一确定就行）。
- 前面加 `!` 的是「只靠标签」的问法（测试里注释「只有标签里的口语才接得住」之后的那几行），多查两条：
  去掉那条知识的标签还答不答得上（答得上就钉不住标签，PACK-090）；是不是正好命中一个标签（V404）。
- 先过一遍助手问答前面的三道拦截：想伤害自己、人身安全与刑事风险、角色契约禁区——被拦下的问法测试里拿不到引用。
- 有一项不行就非零退出。

为什么要有它：第四十七到五十三轮，每轮都手写一段脚本给问法算分，再把挑好的问法抄进测试；
写错一个字就要跑一遍 30 秒的接口测试才知道。这里直接调用助手问答真正用的检索（`_knowledge_hits`），
不另写一份算分，和线上结果一致。
"""
from __future__ import annotations

import json
import sys

from app.modules.notebook.service import MIN_RELATED, terms
from app.modules.packs import schema
from app.modules.packs import service as psvc
from app.modules.skills.service import expand_query


def load(key: str):
    d, problems = schema.validate(json.loads((psvc.SEEDS / f"{key}.json").read_text(encoding="utf-8")))
    if d is None or problems:
        raise SystemExit(f"种子包 {key} 不合格：{problems}")
    return d


def _find(d, want: str):
    for k in d.knowledge:
        if k.key == want:
            return k
    # V424（397 号 spec）用起来才发现：手写时常只记得 key 的开头，也认（能唯一确定才算）
    hits = [k for k in d.knowledge if k.key.startswith(want)] or [k for k in d.knowledge if k.title.startswith(want)]
    if len(hits) != 1:
        raise LookupError(f"「{want}」对不上 {d.key} 里的哪条知识（写 key，或标题开头能唯一确定的几个字）")
    return hits[0]


def refusal(a, q: str) -> str:
    """助手问答在检索之前的三道拦截（与 service.ask 同一组判断）。"""
    from app.core.crisis import is_self_harm
    from app.modules.legal.router import HIGH_RISK_KEYWORDS

    if is_self_harm(q):
        return "会被当成想伤害自己，先给心理援助热线，拿不到引用"
    if any(kw in q for kw in HIGH_RISK_KEYWORDS):
        return "含人身安全或刑事风险的词，会被转介 110，拿不到引用"
    banned = psvc.contract_violation(a, q)
    if banned:
        return f"踩到角色契约禁区「{banned}」，会被拒答"
    return ""


def probe(d, q: str, want: str, tag_only: bool, assistant: str | None = None) -> tuple[bool, str]:
    k = _find(d, want)
    # 没指定助手：用管这条知识的那个（老包一个包有几个助手，各管几条知识）
    a = next((x for x in d.assistants if x.key == assistant), None) if assistant else \
        next((x for x in d.assistants if not x.knowledge or k.key in x.knowledge), d.assistants[0])
    if a is None:
        raise LookupError(f"{d.key} 里没有助手「{assistant}」")
    why = refusal(a, q)
    if why:
        return False, why
    hits = psvc._knowledge_hits(d, a.knowledge, q, None)
    titles = [h.title for h, _ in hits]
    problems = []
    if k.title not in titles:
        top = "、".join(f"「{t}」" for t in titles) or "什么都没有"
        problems.append(f"答不上（前三条是 {top}）")
    if tag_only:
        notag = psvc.knowledge_score(k.title, k.body, [], terms(expand_query(q, None)), q)   # 与助手问答同一套打分
        if notag >= MIN_RELATED:
            problems.append(f"去掉标签也得 {notag} 分（够 {MIN_RELATED} 就算相关），钉不住标签")
        tags = [t for t in k.tags if len(t) >= 2 and t in q]
        if len(tags) != 1:
            problems.append(f"命中的标签是 {tags or '没有'}，要正好一个")
        # PACK-093（422 号 spec）只拿掉命中的那一个、别的标签留着：别的标签的切片补得上，逐个标签变异就测不出来
        rest = [t for t in k.tags if t not in tags]
        others = psvc.knowledge_score(k.title, k.body, rest, terms(expand_query(q, None)), q)
        if tags and others >= MIN_RELATED:
            problems.append(f"只拿掉「{tags[0]}」、靠别的标签也得 {others} 分，换掉和它重叠的标签")
    if problems:
        return False, "；".join(problems)
    rank = titles.index(k.title) + 1
    return True, f"第 {rank} 条" + ("，只靠标签" if tag_only else "")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    d = load(argv[0])
    bad = 0
    for item in argv[1:]:
        tag_only = item.startswith("!")
        q, sep, want = item.lstrip("!").partition("=>")
        if not sep:
            print(f"✗ {item}：要写成「问题=>知识 key」")
            bad += 1
            continue
        try:
            ok, note = probe(d, q.strip(), want.strip(), tag_only)
        except LookupError as e:
            print(f"✗ {q.strip()}：{e}")
            bad += 1
            continue
        print(f"{'✓' if ok else '✗'} {q.strip()} → {_find(d, want.strip()).title}：{note}")
        bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
