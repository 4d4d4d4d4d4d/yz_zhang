"""team monthly budget pool

Revision ID: c71fa9e2b840
Revises: 9b2e4d71c0a3
Create Date: 2026-09-21 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c71fa9e2b840'
down_revision: Union[str, Sequence[str], None] = '9b2e4d71c0a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """TEAM-052 团队月度预算池。

    **`team_members.spend_limit_cents` 的数值不迁移，只换语义**
    （单笔 → 月度累计）：方向是变严的，同一个数字从「每笔」变成「整月」。
    变严的误判可以被 owner 一键调高，变松的误判是钱没了。
    """
    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.add_column(sa.Column('monthly_budget_cents', sa.Integer(), nullable=True))
    # 既有团队一律 0 = 不设池：给老数据凭空安一个池子，
    # 会让他们在毫不知情的情况下被拦住
    op.execute("UPDATE teams SET monthly_budget_cents = 0 WHERE monthly_budget_cents IS NULL")
    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.alter_column('monthly_budget_cents', existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('teams', schema=None) as batch_op:
        batch_op.drop_column('monthly_budget_cents')
