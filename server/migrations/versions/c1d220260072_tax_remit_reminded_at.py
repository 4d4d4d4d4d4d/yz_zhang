"""tax_remit_requests.reminded_at

PAY-042f（V318，291 号 spec）：缴库草稿等确认太久催财务，记上次催的时间。

Revision ID: c1d220260072
Revises: c1d220260071
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260072'
down_revision: Union[str, Sequence[str], None] = 'c1d220260071'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tax_remit_requests', sa.Column('reminded_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('tax_remit_requests', 'reminded_at')
