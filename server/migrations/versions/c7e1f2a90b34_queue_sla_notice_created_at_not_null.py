"""queue_sla_notices.created_at not null

V103 建这张表时把 `created_at` 写成了 `nullable=True`，而模型声明的是
`Mapped[datetime]`（非 Optional，即 NOT NULL）。两边不一致的后果不是
「多一个 null」：`queue_sla_notices` 是**只增不改**的告知记录，
一行没有时间等于这条告知无法排序、无法按「多久以前告知过」筛，
而队列催办（QUEUE-012）正是靠它判断「这件已经告知过了」。

存量行里 `created_at` 可能为 null（探针库里就有），所以先回填再收紧：
回填用 `utcnow()` 而不是丢弃这些行——**已经发出去的告知不能因为迁移消失，
否则用户会被重复催一遍**。

Revision ID: c7e1f2a90b34
Revises: b5c27e91f4a8
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e1f2a90b34'
down_revision: Union[str, Sequence[str], None] = 'b5c27e91f4a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE queue_sla_notices SET created_at = CURRENT_TIMESTAMP "
        "WHERE created_at IS NULL"
    )
    # SQLite 不支持 ALTER COLUMN，批处理模式用「建新表→拷数据→改名」实现
    with op.batch_alter_table("queue_sla_notices") as batch:
        batch.alter_column(
            "created_at", existing_type=sa.DateTime(), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("queue_sla_notices") as batch:
        batch.alter_column(
            "created_at", existing_type=sa.DateTime(), nullable=True
        )
