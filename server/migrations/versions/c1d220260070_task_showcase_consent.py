"""task_showcase_consent

SCN-156（V305，278 号 spec）：发单人同意把这一单放进接单人作品集的时间。

Revision ID: c1d220260070
Revises: c1d220260069
Create Date: 2026-10-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260070'
down_revision: Union[str, Sequence[str], None] = 'c1d220260069'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('showcase_consent_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('showcase_consent_at')
