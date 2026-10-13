"""个人知识库的计算部分（122 号 spec）：随手记、检索与打分、助手引用、纪要抽待办、方法蒸馏、导出。

检索是**字面检索**（词 + 中文二字切分，标题 / 标签 / 正文加权），不是语义检索：
个人笔记不送去向量化供应商（隐私），语义检索留给 V155 统一做。所有结果都带 `mode`，不冒充语义。
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from .models import NbMethod, NbNote

LIMITS = {"notes": 5000, "methods": 100, "steps": 30, "todos": 50}
KINDS = ("note", "link", "minutes")
STATUSES = ("inbox", "filed", "archived")
URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.I)
_CJK = re.compile(r"[一-鿿]")
_TOKEN = re.compile(r"[一-鿿]+|[a-z0-9_+#]+(?:[.-][a-z0-9_+#]+)*")
MAX_TERMS = 12
CANDIDATES = 500
# 长中文串没整串命中时，二字切片至少要命中「一半、且不少于 2 个」（短词就是全部）：
# 「增值税」不命中「增值无关」（1/2），「验收过期会」能命中「……验收，过期自动放款」（2/4）
COVERAGE = 0.5
MIN_RELATED = 3          # 「相关笔记」至少要命中这么多分才给：宁缺毋滥，助手不引一条不沾边的
# 检索词里的虚词：「专票要什么」真正要找的是「专票」。长的先去
_FILLER = sorted(("要什么", "要怎么", "要多少", "需要什么", "什么", "怎么办", "怎么", "怎样", "如何", "哪些", "哪个",
                  "为什么", "是否", "要不要", "能不能", "可以吗", "请问", "一下", "多少", "吗", "呢", "吧", "啊",
                  "的", "了", "我", "你"), key=len, reverse=True)
# 时间词不是主题：「十月报税」要找的是「报税」。只去带前缀的（「周报」「年报」里的周、年是主题）
_TIME = r"[一二三四五六七八九十两\d]+月份?|[上下本这每](?:周|个?月|季度|年)|今天|明天|后天|今年|明年|去年"
_FILLER_RE = re.compile(_TIME + "|" + "|".join(map(re.escape, _FILLER)))


# ------------------------------------------------------------------ 随手记
def is_url(text: str) -> bool:
    return bool(URL_RE.match(text.strip())) and len(text.strip()) <= 500


def link_title(url: str) -> str:
    p = urlparse(url)
    path = p.path.rstrip("/")
    return (p.netloc + (path if len(path) <= 40 else path[:40] + "…"))[:200]


def first_line(text: str) -> str:
    for ln in text.splitlines():
        s = re.sub(r"^[#>\-*•\s]+", "", ln).strip()
        if s:
            return s[:60]
    return ""


def capture(body: str, title: str = "", url: str = "", kind: str | None = None) -> dict:
    """一句话、一段纪要或一个链接进来，猜出类型和标题。**不抓取链接内容**（SSRF 与版权）。"""
    body = body.strip()
    if not url and is_url(body) and "\n" not in body:
        url, body = body, ""
    if url:
        kind = kind or "link"
    if kind is None:
        kind = "minutes" if len(extract_todos(body, None)) >= 2 else "note"
    title = title.strip() or (link_title(url) if url and not body else first_line(body)) or "未命名"
    return {"kind": kind, "title": title[:200], "body": body, "url": url}


# ------------------------------------------------------------------ 检索（KB-102）
def terms(q: str) -> list[tuple[str, int, int]]:
    """（词, 权重, 组号）。中文长串整串权重 3，再切成二字（权重 1、同一组）——「个税申报」也能命中「增值税申报」。"""
    out: list[tuple[str, int, int]] = []
    for g, tok in enumerate(_TOKEN.findall(_FILLER_RE.sub(" ", q.lower()))):
        if _CJK.match(tok):
            out.append((tok, 3, g))
            if len(tok) > 2:
                out.extend((tok[i:i + 2], 1, g) for i in range(len(tok) - 1))
        elif len(tok) >= 2:
            out.append((tok, 3, g))
    seen, uniq = set(), []
    for t, w, g in out:
        if t not in seen:
            seen.add(t)
            uniq.append((t, w, g))
    return uniq[:MAX_TERMS]


def _hit(note: NbNote, t: str, w: int) -> int:
    title, body = note.title.lower(), note.body.lower()
    s = 3 * w if t in title else 0
    if any(t in g.lower() for g in (note.tags or [])):
        s += 2 * w
    s += min(body.count(t), 3) * w
    if t in note.url.lower():
        s += w
    return s


def score(note: NbNote, ts: list[tuple[str, int, int]]) -> int:
    """按组算分：整串命中照算；没整串命中的组，二字切片命中不够（见 COVERAGE）就整组不算——只沾一个字边的不是相关。"""
    total = 0
    for g in dict.fromkeys(x[2] for x in ts):
        group = [(t, w) for t, w, gg in ts if gg == g]
        whole = group[0]
        pieces = group[1:]
        got = {t: _hit(note, t, w) for t, w in group}
        need = min(len(pieces), max(2, math.ceil(COVERAGE * len(pieces))))
        if got[whole[0]] == 0 and pieces and sum(1 for t, _ in pieces if got[t]) < need:
            continue
        total += sum(got.values())
    return total


def snippet(text: str, ts: list[tuple[str, int, int]], width: int = 80) -> str:
    low = text.lower()
    hits = [low.find(t) for t, _, _ in sorted(ts, key=lambda x: -x[1]) if low.find(t) >= 0]
    if not hits:
        return text[:width] + ("…" if len(text) > width else "")
    start = max(min(hits) - width // 4, 0)
    out = text[start:start + width].replace("\n", " ")
    return ("…" if start else "") + out + ("…" if start + width < len(text) else "")


def search(db: Session, owner_id: int, q: str = "", tag: str = "", status: str | None = None,
           kind: str | None = None, limit: int = 50) -> list[tuple[NbNote, int]]:
    qy = db.query(NbNote).filter(NbNote.owner_id == owner_id)
    if status:
        qy = qy.filter(NbNote.status == status)
    else:
        qy = qy.filter(NbNote.status != "archived")
    if kind:
        qy = qy.filter(NbNote.kind == kind)
    ts = terms(q)
    if ts:
        conds = []
        for t, _, _ in ts:
            like = f"%{t}%"
            conds += [NbNote.title.ilike(like), NbNote.body.ilike(like), NbNote.url.ilike(like),
                      cast(NbNote.tags, String).ilike(like)]
        qy = qy.filter(or_(*conds))
    rows = qy.order_by(NbNote.pinned.desc(), NbNote.updated_at.desc(), NbNote.id.desc()).limit(CANDIDATES).all()
    if tag:
        rows = [n for n in rows if tag in (n.tags or [])]
    if not ts:
        return [(n, 0) for n in rows[:limit]]
    scored = [(n, score(n, ts)) for n in rows]
    scored = [x for x in scored if x[1] > 0]
    scored.sort(key=lambda x: (-x[1], -x[0].id))
    return scored[:limit]


def related(db: Session, owner_id: int, text: str, k: int = 3) -> list[dict]:
    """助手引用（KB-104）：给一段文字（任务标题、提问），找出最相关的几条笔记，带出处。"""
    ts = terms(text)
    out = []
    for n, s in search(db, owner_id, text, limit=k * 3):
        if s >= MIN_RELATED and len(out) < k:
            out.append({"note_id": n.id, "title": n.title, "snippet": snippet(n.body or n.url, ts), "score": s})
    return out


def ask(db: Session, owner_id: int, q: str) -> dict:
    """从自己的笔记里找答案：摘录式，每一句都标出处。不编、不补全没有记过的东西。"""
    ts = terms(q)
    hits = [x for x in search(db, owner_id, q, limit=5) if x[1] >= MIN_RELATED]
    if not hits:
        return {"mode": "extractive", "answer": "你的知识库里还没有和这个问题相关的记录。可以先把相关资料随手记进收件箱。",
                "citations": []}
    cites = [{"n": i + 1, "note_id": n.id, "title": n.title, "snippet": snippet(n.body or n.url, ts)}
             for i, (n, _) in enumerate(hits)]
    lines = [f"从你的 {len(cites)} 条笔记里找到："] + [f"[{c['n']}] {c['title']}：{c['snippet']}" for c in cites]
    return {"mode": "extractive", "answer": "\n".join(lines), "citations": cites}


# ------------------------------------------------------------------ 纪要抽待办（KB-105）
_CHECK_OPEN = re.compile(r"^\s*(?:[-*•]\s*)?\[\s\]\s*(.+)$")
_CHECK_DONE = re.compile(r"^\s*(?:[-*•]\s*)?\[[xX√]\]")
_PREFIX = re.compile(r"^\s*(?:[-*•]\s*)?(?:todo|待办|行动项|跟进|action(?:\s*item)?)\s*[:：]\s*(.+)$", re.I)
_LIST = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.、)）])\s*(.+)$")
_ACTION = re.compile(r"负责|跟进|之前|前完成|截止|下周|明天|提交|发给|联系|确认")
_WEEKDAYS = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def due_hint(text: str, now: datetime | None) -> datetime | None:
    """「周五前」「下周三」「10月20日」「10/20」「明天」→ 北京时间当天 18:00，再换回 UTC。认不出就不猜。"""
    if now is None:
        return None
    from app.modules.workbench.service import _back, local

    loc = local(now)
    day = None
    if "后天" in text:
        day = loc + timedelta(days=2)
    elif "明天" in text:
        day = loc + timedelta(days=1)
    elif m := re.search(r"(下)?(?:周|星期|礼拜)([一二三四五六日天])", text):
        wd = _WEEKDAYS[m.group(2)]
        delta = (wd - loc.weekday()) % 7
        if m.group(1):
            delta = 7 - loc.weekday() + wd
        elif delta == 0:
            delta = 0 if loc.hour < 18 else 7
        day = loc + timedelta(days=delta)
    elif m := (re.search(r"(\d{1,2})月(\d{1,2})[日号]", text) or re.search(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])", text)):
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            day = loc.replace(month=mo, day=d)
            if day < loc - timedelta(days=30):
                day = day.replace(year=loc.year + 1)
        except ValueError:
            return None
    if day is None:
        return None
    return _back(day.replace(hour=18, minute=0, second=0, microsecond=0))


def extract_todos(body: str, now: datetime | None) -> list[dict]:
    out, seen = [], set()
    for ln in body.splitlines():
        if not ln.strip() or _CHECK_DONE.match(ln):
            continue
        m = _CHECK_OPEN.match(ln) or _PREFIX.match(ln)
        if not m:
            lm = _LIST.match(ln)
            m = lm if lm and _ACTION.search(lm.group(1)) else None
        if not m:
            continue
        title = m.group(1).strip()[:200]
        key = re.sub(r"\W", "", title)
        if not title or key in seen:
            continue
        seen.add(key)
        due = due_hint(title, now)
        out.append({"title": title, "due_at": due, "line": ln.strip()[:300]})
        if len(out) >= LIMITS["todos"]:
            break
    return out


# ------------------------------------------------------------------ 方法蒸馏（KB-106）
_NUMBERED = re.compile(r"^\s*(?:\d{1,2}[.、)）]|第[一二三四五六七八九十\d]+步[:：，,]?)\s*(.+)$")
_BULLET = re.compile(r"^\s*(?:[-*•]\s+|\[\s\]\s*)(?!\[[xX√ ]\])(.+)$")


def _split_step(text: str) -> dict:
    head, sep, tail = text.partition("：")
    if not sep:
        head, sep, tail = text.partition(":")
    if sep and 0 < len(head.strip()) <= 30 and tail.strip():
        return {"title": head.strip()[:200], "note": tail.strip()[:500]}
    return {"title": text.strip()[:200], "note": ""}


def distill(notes: list[NbNote]) -> dict:
    """把几条笔记里的步骤列表收成一份方法草稿：有编号的步骤优先，没有再取圆点列表。只出草稿，不写库。"""
    numbered, bullets = [], []
    for n in notes:
        for ln in n.body.splitlines():
            if _CHECK_DONE.match(ln):
                continue
            if m := _NUMBERED.match(ln):
                numbered.append(m.group(1))
            elif m := _BULLET.match(ln):
                bullets.append(m.group(1))
    raw = numbered or bullets
    steps, seen = [], set()
    for t in raw:
        key = re.sub(r"\W", "", t.lower())
        if key and key not in seen:
            seen.add(key)
            steps.append(_split_step(t))
        if len(steps) >= LIMITS["steps"]:
            break
    base = notes[0].title if notes else "我的方法"
    name = base if re.search(r"(方法|流程|做法|清单|SOP|步骤)$", base, re.I) else f"{base}的做法"
    return {"name": name[:60], "steps": steps, "source_note_ids": [n.id for n in notes],
            "found": "numbered" if numbered else ("bullets" if bullets else "none")}


# ------------------------------------------------------------------ 导出（KB-108）
def export_markdown(notes: list[NbNote], methods: list[NbMethod]) -> str:
    from app.core.timefmt import iso

    out = ["# 我的知识库", ""]
    for n in notes:
        out += [f"## {n.title}", ""]
        meta = [f"类型：{ {'note': '笔记', 'link': '链接', 'minutes': '纪要'}.get(n.kind, n.kind) }",
                f"记于：{iso(n.created_at)}"]
        if n.tags:
            meta.append("标签：" + "、".join(n.tags))
        if n.url:
            meta.append(f"链接：{n.url}")
        out += ["> " + " · ".join(meta), ""]
        if n.body:
            out += [n.body, ""]
    if methods:
        out += ["# 我的方法", ""]
        for m in methods:
            out += [f"## {m.name}", ""] + ([m.description, ""] if m.description else [])
            out += [f"{i + 1}. {s['title']}" + (f"：{s['note']}" if s.get("note") else "") for i, s in enumerate(m.steps)]
            out.append("")
    return "\n".join(out)
