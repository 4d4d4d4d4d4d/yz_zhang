"""legal_faq_review

LAW-062（V196，169 号 spec）：法律条目的复核日期与提醒进度。

Revision ID: c1d220260037
Revises: c1d220260036
Create Date: 2026-10-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260037'
down_revision: Union[str, Sequence[str], None] = 'c1d220260036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('legal_faqs') as batch:
        batch.add_column(sa.Column('valid_until', sa.Date(), nullable=True))
        batch.add_column(sa.Column('review_stage', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('legal_faqs') as batch:
        batch.drop_column('review_stage')
        batch.drop_column('valid_until')
