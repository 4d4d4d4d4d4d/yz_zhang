"""reports.images

RISK-017（V431，404 号 spec）：举报附截图（存图片名，最多 3 张，只收举报人自己上传的）。

Revision ID: c1d220260099
Revises: c1d220260098
Create Date: 2026-11-04 22:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260099'
down_revision: Union[str, Sequence[str], None] = 'c1d220260098'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('reports') as batch:
        batch.add_column(sa.Column('images', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('reports') as batch:
        batch.drop_column('images')
