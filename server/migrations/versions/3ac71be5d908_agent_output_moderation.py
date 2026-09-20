"""agent output moderation

Revision ID: 3ac71be5d908
Revises: 5cb0dc0c6f12
Create Date: 2026-09-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ac71be5d908'
down_revision: Union[str, Sequence[str], None] = '5cb0dc0c6f12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """AGT-051 agent_runs 增加内容审核结论两列。

    仍然是那条可移植写法：**先加可空列 → 回填 → 再置非空**。
    autogenerate 直接产出的 NOT NULL 无默认值在已有数据上必然失败。
    """
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('moderation_status', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('moderation_labels', sa.JSON(), nullable=True))
    # 历史 run 没有送过审：留空串而不是假装 'pass'——
    # 把「没审过」记成「审过且通过」，是给后来看这张表的人埋一个假事实
    op.execute("UPDATE agent_runs SET moderation_status = '' WHERE moderation_status IS NULL")
    op.execute("UPDATE agent_runs SET moderation_labels = '[]' WHERE moderation_labels IS NULL")
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.alter_column('moderation_status', existing_type=sa.String(length=10),
                              nullable=False)
        batch_op.alter_column('moderation_labels', existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.drop_column('moderation_labels')
        batch_op.drop_column('moderation_status')
