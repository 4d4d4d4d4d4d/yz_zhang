"""milestones.delivery_note

SC-015（V323，296 号 spec）：执行方一次交付多期时写的交付说明。

Revision ID: c1d220260074
Revises: c1d220260073
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260074'
down_revision: Union[str, Sequence[str], None] = 'c1d220260073'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('milestones', sa.Column('delivery_note', sa.String(length=500), nullable=False, server_default=''))


def downgrade() -> None:
    op.drop_column('milestones', 'delivery_note')
