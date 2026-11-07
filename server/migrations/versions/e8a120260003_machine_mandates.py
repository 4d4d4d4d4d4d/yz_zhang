"""Bounded task mandates and idempotent machine action audit."""
from alembic import op
import sqlalchemy as sa

revision = 'e8a120260003'
down_revision = 'd8a120260003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('machine_mandates',
        sa.Column('key_id', sa.Integer(), primary_key=True),
        sa.Column('principal_id', sa.Integer(), nullable=False),
        sa.Column('operations', sa.JSON(), nullable=False),
        sa.Column('categories', sa.JSON(), nullable=False),
        sa.Column('per_task_cents', sa.Integer(), nullable=False),
        sa.Column('total_cents', sa.Integer(), nullable=False),
        sa.Column('used_cents', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False))
    op.create_index('ix_machine_mandates_principal_id', 'machine_mandates', ['principal_id'])
    op.create_table('machine_actions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key_id', sa.Integer(), nullable=False),
        sa.Column('principal_id', sa.Integer(), nullable=False),
        sa.Column('request_key', sa.String(80), nullable=False),
        sa.Column('operation', sa.String(20), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('response', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('key_id','request_key',name='uq_machine_request'))
    for col in ['key_id', 'principal_id']:
        op.create_index('ix_machine_actions_'+col, 'machine_actions', [col])


def downgrade():
    op.drop_table('machine_actions')
    op.drop_table('machine_mandates')
