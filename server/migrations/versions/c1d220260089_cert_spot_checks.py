"""cert_spot_checks

CERT-053（V375，348 号 spec）：资质审核抽检。

Revision ID: c1d220260089
Revises: c1d220260088
Create Date: 2026-10-31 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260089'
down_revision: Union[str, Sequence[str], None] = 'c1d220260088'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cert_spot_checks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=30), nullable=False),
        sa.Column('reviewer_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=12), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('checked_by', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('checked_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id'),
    )
    op.create_index(op.f('ix_cert_spot_checks_user_id'), 'cert_spot_checks', ['user_id'], unique=False)
    op.create_index(op.f('ix_cert_spot_checks_reviewer_id'), 'cert_spot_checks', ['reviewer_id'], unique=False)
    op.create_index(op.f('ix_cert_spot_checks_status'), 'cert_spot_checks', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cert_spot_checks_status'), table_name='cert_spot_checks')
    op.drop_index(op.f('ix_cert_spot_checks_reviewer_id'), table_name='cert_spot_checks')
    op.drop_index(op.f('ix_cert_spot_checks_user_id'), table_name='cert_spot_checks')
    op.drop_table('cert_spot_checks')
