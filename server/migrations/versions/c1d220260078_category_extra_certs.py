"""category_extra_certs

SCN-181（V334，307 号 spec）：一个类目可以要多张资质（required_cert 之外再要的）。

Revision ID: c1d220260078
Revises: c1d220260077
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260078'
down_revision: Union[str, Sequence[str], None] = 'c1d220260077'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('categories') as batch:
        batch.add_column(sa.Column('extra_certs', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('categories') as batch:
        batch.drop_column('extra_certs')
