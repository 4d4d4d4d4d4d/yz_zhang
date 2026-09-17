import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    """CONC-001/002/003 引擎构造：SQLite（开发/测试）与 Postgres（生产）分支。

    业务代码不感知方言差异；池参数只对真实网络型数据库有意义，
    SQLite 走 connect_args + PRAGMA。
    """
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///") and "memory" not in url:
            path = url.removeprefix("sqlite:///")
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        # CONC-020 SQLite 必须用 NullPool：**连接池会跨请求留下过期的 WAL 读快照**。
        #
        # 实测复现：全链路验收里「注销后登录态失效」间歇性失败。注销请求确实
        # 提交了（库里 users.is_deleted=1、login_sessions.revoked=1），但紧接着
        # 的 GET /users/me 仍然返回 200——在鉴权处打点看到它读到的是
        # is_deleted=False / revoked=False，也就是**读到了提交之前的快照**。
        # 换成 NullPool 后同一条链路稳定通过，打点也变成 True/True。
        #
        # 后果比「一条验收项偶尔红」严重得多：它意味着在 SQLite 下
        # **写完立刻读不保证读到自己刚写的东西**——一个已吊销的会话
        # 可以在一段时间内继续通过鉴权。
        #
        # 只影响 SQLite（开发/测试）。生产是 Postgres，有真正的 MVCC 与
        # 每事务快照，连接池没有这个问题，所以下面的分支保持不变。
        # 代价是每次检出都新开一个连接——SQLite 是本地文件，开销可忽略。
        from sqlalchemy.pool import NullPool

        eng = create_engine(url, connect_args={"check_same_thread": False},
                            poolclass=NullPool)

        @event.listens_for(eng, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - 驱动回调
            cur = dbapi_conn.cursor()
            # WAL：读写不互斥，降低本地并发写的 "database is locked"
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute(f"PRAGMA busy_timeout={settings.SQLITE_BUSY_TIMEOUT_MS}")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return eng
    return create_engine(
        url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
    )


engine = _make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def dialect_name() -> str:
    return engine.dialect.name


def supports_row_lock() -> bool:
    """CONC-004 方言探测：SQLite 无 SELECT ... FOR UPDATE（整库写锁串行化），
    真实行锁只在 Postgres/MySQL 生效；SQLite 下降级为普通读，
    正确性由状态机白名单 + 乐观锁版本号兜底。"""
    return dialect_name() in ("postgresql", "mysql", "mariadb")


def init_db() -> None:
    """开发/测试建表。

    DEP-020：**生产唯一建表路径是 `alembic upgrade head`**，
    多副本下并发 create_all 会互相踩；这里显式拒绝，避免误用。
    """
    from app.modules import models_all  # noqa: F401

    if settings.ENV == "prod":
        raise RuntimeError("生产环境禁止 create_all，请执行 alembic upgrade head")
    Base.metadata.create_all(engine)


def migration_status() -> dict:
    """DEP-022 代码期望的迁移版本 vs 库里实际版本。

    库里没有 alembic_version 表 → 说明是 create_all 建的开发库，
    返回 not_applicable（开发环境不因此不就绪）。
    """
    from sqlalchemy import inspect

    try:
        insp = inspect(engine)
        if "alembic_version" not in insp.get_table_names():
            return {"state": "not_applicable", "db": None, "head": _script_head()}
        with engine.connect() as conn:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # pragma: no cover - 依赖故障路径
        return {"state": "unknown", "error": type(exc).__name__}
    head = _script_head()
    if head is None:
        return {"state": "unknown", "db": current, "head": None}
    return {"state": "ok" if current == head else "mismatch", "db": current, "head": head}


def _script_head() -> str | None:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cfg = Config(os.path.join(root, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(root, "migrations"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:  # alembic 未安装或脚本目录缺失时不阻塞启动
        return None


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
