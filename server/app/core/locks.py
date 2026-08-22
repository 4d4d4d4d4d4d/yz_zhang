"""CONC-010~013 / 040~041 并发控制原语。

三层防护，缺一不可：
1. **行锁**（本模块 `lock_contract` / `lock_wallets`）——多副本下把
   「读-判断-写」串行化。SQLite 无行锁，自动降级。
2. **乐观锁**（模型上的 `lock_version` + `version_id_col`）——即便没拿到行锁，
   并发 UPDATE 也只有一个能成功，另一个 `StaleDataError` → 409。
3. **状态机白名单**（业务层）——重复操作即使串行到达也被状态判断拒绝。

行锁顺序约定：**先合约、后钱包；多个钱包按 user_id 升序**。
所有资金路径遵守同一顺序，从根上杜绝死锁。
"""
import os
import socket
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import supports_row_lock

# 本副本标识：写进锁记录，排障时能看出是谁在持锁
INSTANCE_ID = f"{socket.gethostname()}-{os.getpid()}"


def lock_contract(db: Session, contract_id: int):
    """CONC-010 取合约行锁并返回最新行（SQLite 下等价于普通读）。"""
    from app.modules.contract.models import Contract

    stmt = select(Contract).where(Contract.id == contract_id)
    if supports_row_lock():
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def lock_wallets(db: Session, *user_ids: int) -> None:
    """CONC-011 钱包行锁：去重后按 user_id 升序依次加锁，避免交叉转账死锁。

    只做「锁定」，返回值无意义——调用方随后用 `wallet.get_or_create` 拿对象，
    此时行已被本事务持有。
    """
    if not supports_row_lock():
        return
    from app.modules.wallet.models import WalletAccount

    for uid in sorted(set(user_ids)):
        db.execute(
            select(WalletAccount)
            .where(WalletAccount.user_id == uid)
            .with_for_update()
        ).scalar_one_or_none()


def lock_contract_funds(db: Session, contract) -> None:
    """资金路径统一入口：锁住合约本行 + 双方钱包 + 平台账户。"""
    from app.modules.wallet.service import PLATFORM_USER_ID

    lock_contract(db, contract.id)
    lock_wallets(db, contract.requester_id, contract.executor_id, PLATFORM_USER_ID)


# ── CONC-040/041 定时任务执行锁 ──────────────────────────────────────


def acquire_job_lock(db: Session, job_name: str, holder: str, ttl_seconds: int | None = None) -> bool:
    """抢占式单实例锁：拿到返回 True，已被他人持有且未过期返回 False。

    实现用「条件 UPDATE 的影响行数」判定，PG/SQLite 通用且原子；
    持锁进程崩溃时靠 `expires_at` 过期自动释放，不会永久阻塞。
    """
    from app.core.models_infra import JobLock
    from app.modules.account.models import utcnow

    ttl = ttl_seconds if ttl_seconds is not None else settings.JOB_LOCK_TTL_SECONDS
    now = utcnow()
    expires = now + timedelta(seconds=ttl)

    # 先尝试抢占已过期（或首次创建后即到期）的锁——条件 UPDATE 是原子的
    updated = (
        db.query(JobLock)
        .filter(JobLock.job_name == job_name, JobLock.expires_at <= now)
        .update(
            {"holder": holder, "locked_at": now, "expires_at": expires},
            synchronize_session=False,
        )
    )
    if updated:
        db.expire_all()
        return True
    if db.query(JobLock.job_name).filter(JobLock.job_name == job_name).first():
        return False  # 存在且未过期 → 他人持有
    # 首次创建：用 SAVEPOINT 包住，撞唯一键时只回滚这一小段，不影响外层事务
    try:
        with db.begin_nested():
            db.add(JobLock(job_name=job_name, holder=holder, locked_at=now, expires_at=expires))
        return True
    except Exception:  # 并发下另一个实例先插入成功
        return False


def job_slot(job_name: str):
    """CONC-040 job 端点守卫（FastAPI 依赖工厂）。

    多副本部署时 cron 可能同时打到多个副本；没有这道锁，
    「自动验收」「过期下架」这类会动资金/状态的任务会被重复执行。
    抢不到锁返回 409 `job_running`——对调用方（cron）是明确的「本次跳过」信号。

    执行完毕即释放：串行调用永远能拿到锁，只有真正并发才会被挡。
    崩溃不释放时靠 TTL 过期兜底。
    """
    from fastapi import Depends

    from .db import get_db
    from .errors import conflict

    def dependency(db: Session = Depends(get_db)):
        if not acquire_job_lock(db, job_name, INSTANCE_ID):
            raise conflict(f"任务 {job_name} 正在其它实例执行", "job_running")
        try:
            yield
        except Exception as exc:
            # DEP-051 失败也要留痕：先回滚丢弃 job 的部分改动（同时释放写锁），
            # 再单独提交这条失败记录——否则它会跟着 get_db 的回滚一起消失。
            db.rollback()
            _note_job_result(db, job_name, ok=False, error=type(exc).__name__)
            db.commit()
            raise
        release_job_lock(db, job_name, INSTANCE_ID)
        _note_job_result(db, job_name, ok=True)

    return dependency


def _note_job_result(db: Session, job_name: str, ok: bool, error: str = "") -> None:
    """DEP-051 job 健康落库（在调用方的会话里，避免第二条连接与之争锁）。"""
    from app.core.models_infra import JobLock
    from app.modules.account.models import utcnow

    row = db.get(JobLock, job_name)
    if row is None:
        row = JobLock(job_name=job_name, holder=INSTANCE_ID)
        db.add(row)
    if ok:
        row.last_success_at = utcnow()
        row.last_error = ""
    else:
        row.last_error = error[:200]
    db.add(row)
    db.flush()


def job_health(db: Session) -> list[dict]:
    """DEP-051 各 job 的上次成功时间与最近错误，供监控与后台展示。"""
    from app.core.models_infra import JobLock
    from app.modules.account.models import utcnow

    now = utcnow()
    out = []
    for row in db.query(JobLock).all():
        age = (now - row.last_success_at).total_seconds() if row.last_success_at else None
        out.append({
            "job": row.job_name,
            "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
            "seconds_since_success": int(age) if age is not None else None,
            "last_error": row.last_error,
            "holder": row.holder,
        })
    return sorted(out, key=lambda r: r["job"])


def release_job_lock(db: Session, job_name: str, holder: str) -> None:
    """提前释放（仅持有者可释放，避免误放他人的锁）。"""
    from app.core.models_infra import JobLock
    from app.modules.account.models import utcnow

    db.query(JobLock).filter(
        JobLock.job_name == job_name, JobLock.holder == holder
    ).update({"expires_at": utcnow()}, synchronize_session=False)
