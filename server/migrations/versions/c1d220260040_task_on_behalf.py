"""task_on_behalf

SCN-119（V202，175 号 spec）：替别人发单——服务对象的称呼、在场联系方式、确认问过本人的时间。

Revision ID: c1d220260040
Revises: c1d220260039
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260040'
down_revision: Union[str, Sequence[str], None] = 'c1d220260039'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.add_column(sa.Column('on_behalf', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column('recipient_label', sa.String(length=20), nullable=False, server_default=''))
        batch.add_column(sa.Column('onsite_contact', sa.String(length=40), nullable=False, server_default=''))
        batch.add_column(sa.Column('recipient_consent_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('tasks') as batch:
        batch.drop_column('recipient_consent_at')
        batch.drop_column('onsite_contact')
        batch.drop_column('recipient_label')
        batch.drop_column('on_behalf')
