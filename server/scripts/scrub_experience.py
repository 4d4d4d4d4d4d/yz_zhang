"""KB-061 把**已经落库**的经验数据洗一遍（83 号 spec）。

写入点修好之后，库里还留着修好之前的行。V108 的探针就是在这些行上
复现出来的：经验卡带着手机号给别的用户看，核验经验带着地址进提示词。

所以这是一条**一次性脚本**而不是定时任务：
- 它要在开站前（或升级后）跑一次，跑完这件事就结束了；
- 做成定时任务会让人以为「脏数据会被自动处理」，从而放心地继续写脏数据——
  而真正该拦的是写入点，那里已经有闸门了。

    python -m scripts.scrub_experience --dry-run   # 先看会改什么
    python -m scripts.scrub_experience             # 真的改

改动逐条打印：这是动用户数据的脚本，**不留痕的批量改写是最不该有的东西**。
"""
import sys

from app.core.db import SessionLocal
from app.core.scrub import scrub_text


def main(dry_run: bool) -> int:
    from app.modules.knowledge.models import KnowledgeCard
    from app.modules.task.models import Task
    from app.modules.verify.models import VerificationLesson

    changed = 0
    with SessionLocal() as db:
        # 经验卡：标题改成派生值（类目·城市），与写入点一致
        for card in db.query(KnowledgeCard).all():
            task = db.get(Task, card.source_task_id) if card.source_task_id else None
            want = f"{card.category}·{card.city or '不限城市'}"
            if card.title != want:
                print(f"  card#{card.id}: {card.title!r} -> {want!r}")
                if not dry_run:
                    card.title = want
                changed += 1
            # 分解快照里的子任务标题同样是用户输入
            if card.decomposition:
                names = ()
                if task:
                    from app.core.scrub import party_names

                    names = party_names(db, task)
                cleaned = [{**item, "title": scrub_text(item.get("title", ""), names)}
                           for item in card.decomposition]
                if cleaned != card.decomposition:
                    print(f"  card#{card.id}: 分解快照里的标题已脱敏")
                    if not dry_run:
                        card.decomposition = cleaned
                    changed += 1

        # 核验经验：三个自由文本字段
        for row in db.query(VerificationLesson).all():
            task = None
            fields = {
                "task_title": scrub_text(row.task_title or ""),
                "reason": scrub_text(row.reason or ""),
                "revision_summary": scrub_text(row.revision_summary or ""),
            }
            for name, want in fields.items():
                if getattr(row, name) != want:
                    print(f"  lesson#{row.id}.{name} 已脱敏")
                    if not dry_run:
                        setattr(row, name, want)
                    changed += 1
            if row.criteria:
                cleaned = [scrub_text(c) for c in row.criteria]
                if cleaned != row.criteria:
                    print(f"  lesson#{row.id}.criteria 已脱敏")
                    if not dry_run:
                        row.criteria = cleaned
                    changed += 1
        if not dry_run:
            db.commit()

    verb = "会改" if dry_run else "已改"
    print(f"{verb} {changed} 处。" + ("（--dry-run，没有写库）" if dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main("--dry-run" in sys.argv))
