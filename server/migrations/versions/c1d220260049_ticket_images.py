"""ticket_images

ESCA-057（V254，227 号 spec）：工单与追加回复附的截图（自己上传过的图片名）。

Revision ID: c1d220260049
Revises: c1d220260048
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260049'
down_revision: Union[str, Sequence[str], None] = 'c1d220260048'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tickets') as batch:
        batch.add_column(sa.Column('images', sa.JSON(), nullable=True))
    with op.batch_alter_table('ticket_replies') as batch:
        batch.add_column(sa.Column('images', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('ticket_replies') as batch:
        batch.drop_column('images')
    with op.batch_alter_table('tickets') as batch:
        batch.drop_column('images')
