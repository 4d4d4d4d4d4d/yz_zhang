"""finance_correction_report

FIN-068（V296，269 号 spec）：更正说明分表（平台收支表 / 成交额与代扣税表）。

Revision ID: c1d220260068
Revises: c1d220260067
Create Date: 2026-10-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260068'
down_revision: Union[str, Sequence[str], None] = 'c1d220260067'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('finance_period_corrections') as batch:
        batch.add_column(sa.Column('report', sa.String(length=16), nullable=False, server_default='platform'))


def downgrade() -> None:
    with op.batch_alter_table('finance_period_corrections') as batch:
        batch.drop_column('report')
