"""errand_reviews.reminded_at

SCN-220（V365，338 号 spec）：在等太久的发单复核催运营，每条一天一次。

Revision ID: c1d220260088
Revises: c1d220260087
Create Date: 2026-10-30 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260088'
down_revision: Union[str, Sequence[str], None] = 'c1d220260087'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('errand_reviews') as batch_op:
        batch_op.add_column(sa.Column('reminded_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('errand_reviews') as batch_op:
        batch_op.drop_column('reminded_at')
