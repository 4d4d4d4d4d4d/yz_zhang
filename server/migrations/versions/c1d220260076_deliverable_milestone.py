"""deliverable_milestone

SC-017（V331，304 号 spec）：交付文件可以挂到某一期上；那一期放款后原图就解锁。

Revision ID: c1d220260076
Revises: c1d220260075
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260076'
down_revision: Union[str, Sequence[str], None] = 'c1d220260075'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('contract_deliverables') as batch:
        batch.add_column(sa.Column('milestone_idx', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('contract_deliverables') as batch:
        batch.drop_column('milestone_idx')
