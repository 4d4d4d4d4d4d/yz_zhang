"""DRILL-010 恢复后一致性校验的**唯一实现**。

此前这段校验是 `deploy/restore.sh` 里的一个 heredoc：

    docker compose ... exec -T api python - <<'PY'
    money = risk.reconcile(db)
    chain = anchor.verify_chain(db)
    ...
    PY

写得很对，但它**只存在于一个需要完整生产栈 + 人手动敲 yes 才能跑到的地方**，
所以从来没有被执行过一次。一段从没跑过的校验代码和没有校验没有区别。

把它提出来的目的不是「整理代码」，是让**演练里跑的那段校验，就是生产恢复时
跑的那段校验**。两份实现迟早会漂移，而漂移的那一天你正在恢复生产库。

    python -m scripts.consistency_check          # 退出码 0 = 通过
"""
import sys

from app.core.db import SessionLocal


def check() -> dict:
    """返回 {'ok': bool, 'money': ..., 'chain': ...}，不打印、不退出。"""
    from app.modules.anchor import service as anchor
    from app.modules.risk import service as risk

    with SessionLocal() as db:
        money = risk.reconcile(db)
        chain = anchor.verify_chain(db)
    return {
        "ok": bool(money.get("ok")) and bool(chain.get("valid")),
        "money": money,
        "chain": {k: v for k, v in chain.items() if k != "head"},
    }


def main() -> int:
    result = check()
    print("资金对账:", result["money"].get("ok"), result["money"])
    print("存证链:", result["chain"].get("valid"), result["chain"])
    if not result["ok"]:
        print("一致性校验未通过——不要对外提供服务，先人工核对。")
        return 1
    print("一致性校验通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
