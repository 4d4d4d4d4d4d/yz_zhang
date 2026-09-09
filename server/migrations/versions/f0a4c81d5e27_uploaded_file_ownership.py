"""files: uploaded file ownership (FILE-012)

改造前上传要求登录，却没有任何地方记下是谁传的——举报一张违规图片时，
平台没有任何途径追溯到上传者。

注意：本迁移**只建表，不重命名历史文件**（FILE-030）。历史文件的名字仍是
内容哈希，重命名会让已经写进 ProgressLog.images 与纠纷证据里的 URL 全部失效。

Revision ID: f0a4c81d5e27
Revises: e5b73c9a1204
Create Date: 2026-09-09 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0a4c81d5e27'
down_revision: Union[str, Sequence[str], None] = 'e5b73c9a1204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'uploaded_files',
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('content_type', sa.String(length=32), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('name'),
    )
    op.create_index('ix_uploaded_files_owner_id', 'uploaded_files', ['owner_id'])
    op.create_index('ix_uploaded_files_sha256', 'uploaded_files', ['sha256'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_uploaded_files_sha256', table_name='uploaded_files')
    op.drop_index('ix_uploaded_files_owner_id', table_name='uploaded_files')
    op.drop_table('uploaded_files')
