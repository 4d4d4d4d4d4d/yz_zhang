"""DEP-020 Alembic 运行环境。

数据库地址一律从 `settings.DATABASE_URL` 取（与应用同源），
不在 alembic.ini 里另写一份——两份配置迟早会漂移。
"""
import os
import sys

from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.core.db import Base, engine  # noqa: E402
from app.modules import models_all  # noqa: E402,F401  —— 导入即注册全部模型

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite 不支持大多数 ALTER，批处理模式用「建新表→拷数据→改名」实现
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 调用方可通过 config.attributes["connection"] 注入连接（测试用；
    # 也是 alembic 官方推荐的「程序内调用」方式）
    injected = context.config.attributes.get("connection")
    if injected is not None:
        _run(injected)
        return
    with engine.connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
