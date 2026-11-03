"""verification_orders.designated_verifier_id

VER-050（V399，372 号 spec）：发单人点名一位核验人；只有被点名的人能接这一单。

Revision ID: c1d220260093
Revises: c1d220260092
Create Date: 2026-11-03 17:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260093'
down_revision: Union[str, Sequence[str], None] = 'c1d220260092'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('verification_orders') as batch:
        batch.add_column(sa.Column('designated_verifier_id', sa.Integer(), nullable=True))
        batch.create_index('ix_verification_orders_designated_verifier_id', ['designated_verifier_id'])


def downgrade() -> None:
    with op.batch_alter_table('verification_orders') as batch:
        batch.drop_index('ix_verification_orders_designated_verifier_id')
        batch.drop_column('designated_verifier_id')
