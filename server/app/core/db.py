import os

from sqlalchemy import create_engine, event
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
        eng = create_engine(url, connect_args={"check_same_thread": False})

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
    # 导入全部模型后建表
    from app.modules import models_all  # noqa: F401

    Base.metadata.create_all(engine)


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
