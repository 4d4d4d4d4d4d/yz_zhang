"""dispute: response deadline reminder flag (DSPR-022)

幂等标记。没有它，「距答辩截止不足 N 小时」会在每次 job 运行时反复成立，
把一条提醒变成每小时一条骚扰。

Revision ID: a71e3f9d2b46
Revises: f0a4c81d5e27
Create Date: 2026-09-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a71e3f9d2b46'
down_revision: Union[str, Sequence[str], None] = 'f0a4c81d5e27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'disputes',
        sa.Column('response_reminded', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('disputes', 'response_reminded')
