"""contract_deliverables

SCN-166（V324，297 号 spec）：交付文件托管在平台，原图放款完毕前锁着。

Revision ID: c1d220260075
Revises: c1d220260074
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260075'
down_revision: Union[str, Sequence[str], None] = 'c1d220260074'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'contract_deliverables',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('file_name', sa.String(length=80), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_contract_deliverables_contract_id'), 'contract_deliverables', ['contract_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_contract_deliverables_contract_id'), table_name='contract_deliverables')
    op.drop_table('contract_deliverables')
