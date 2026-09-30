"""orchestrator agents and lesson feedback

Revision ID: 9b2e4d71c0a3
Revises: 3ac71be5d908
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b2e4d71c0a3'
down_revision: Union[str, Sequence[str], None] = '3ac71be5d908'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """ORC-060/061/063：编排允许派给 agent、步骤记下派给了谁、run 记下喂了哪些经验。

    仍是那条可移植写法：先加可空列 → 回填 → 再置非空。
    `mission_steps.agent_user_id` 本来就允许为空（没派给 agent 的步骤没有它），
    所以只有另外两列需要回填。
    """
    with op.batch_alter_table('missions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('allow_agents', sa.Boolean(), nullable=True))
    # 历史编排一律按**没有授权**回填：把「没表态」当成「同意」，
    # 正是这个开关要防的事
    op.execute("UPDATE missions SET allow_agents = 0 WHERE allow_agents IS NULL")
    with op.batch_alter_table('missions', schema=None) as batch_op:
        batch_op.alter_column('allow_agents', existing_type=sa.Boolean(), nullable=False)

    with op.batch_alter_table('mission_steps', schema=None) as batch_op:
        batch_op.add_column(sa.Column('agent_user_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lessons_used', sa.JSON(), nullable=True))
    # 历史 run 没有喂过经验：空列表是事实，不是缺省
    op.execute("UPDATE agent_runs SET lessons_used = '[]' WHERE lessons_used IS NULL")
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.alter_column('lessons_used', existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.drop_column('lessons_used')
    with op.batch_alter_table('mission_steps', schema=None) as batch_op:
        batch_op.drop_column('agent_user_id')
    with op.batch_alter_table('missions', schema=None) as batch_op:
        batch_op.drop_column('allow_agents')
