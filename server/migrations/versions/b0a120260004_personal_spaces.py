"""Opt-in independently editable public personal spaces."""
from alembic import op
import sqlalchemy as sa
revision = 'b0a120260004'
down_revision = 'a9a120260003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('personal_spaces',
        sa.Column('user_id', sa.Integer(), primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('published', sa.Boolean(), nullable=False),
        sa.Column('headline', sa.String(120), nullable=False),
        sa.Column('introduction', sa.String(1600), nullable=False),
        sa.Column('theme', sa.String(20), nullable=False),
        sa.Column('items', sa.JSON(), nullable=False))
    op.create_index('ix_personal_spaces_published', 'personal_spaces', ['published'])


def downgrade():
    op.drop_table('personal_spaces')
