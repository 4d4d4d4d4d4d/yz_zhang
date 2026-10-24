"""Separate declared corporate/partnership records from project contribution units."""
from alembic import op
import sqlalchemy as sa
revision='f8a120260003'
down_revision='e8a120260003'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('organization_records',
      sa.Column('id',sa.Integer(),primary_key=True),
      sa.Column('venture_id',sa.Integer(),nullable=False),
      sa.Column('revision',sa.Integer(),nullable=False),
      sa.Column('submitted_by',sa.Integer(),nullable=False),
      sa.Column('entity_type',sa.String(32),nullable=False),
      sa.Column('jurisdiction',sa.String(80),nullable=False),
      sa.Column('registered_name',sa.String(200),nullable=False),
      sa.Column('registration_number',sa.String(100),nullable=False),
      sa.Column('representative_user_id',sa.Integer(),nullable=False),
      sa.Column('governance_basis',sa.String(4000),nullable=False),
      sa.Column('document_references',sa.JSON(),nullable=False),
      sa.Column('rights',sa.JSON(),nullable=False),
      sa.Column('record_hash',sa.String(64),nullable=False),
      sa.Column('created_at',sa.DateTime(),nullable=False),
      sa.UniqueConstraint('venture_id','revision',name='uq_org_revision'))
    op.create_index('ix_organization_records_venture_id','organization_records',['venture_id'])


def downgrade():
    op.drop_table('organization_records')
