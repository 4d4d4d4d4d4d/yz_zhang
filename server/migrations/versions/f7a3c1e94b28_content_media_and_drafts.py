"""content: media urls and drafts (CNT-003/014)

原 spec 写着「博客编辑器：Markdown/富文本，草稿箱，插图，标签」——
而这张表**压根没有存媒体的地方**，`status` 也只有 published/removed。
插图、视频、草稿箱三件事都无从谈起。

Revision ID: f7a3c1e94b28
Revises: e6d2a83f1b40
Create Date: 2026-09-17 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7a3c1e94b28'
down_revision: Union[str, Sequence[str], None] = 'e6d2a83f1b40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contents', sa.Column('media_urls', sa.JSON(), nullable=True))
    op.execute("UPDATE contents SET media_urls = '[]' WHERE media_urls IS NULL")
    with op.batch_alter_table('contents') as batch_op:
        batch_op.alter_column('media_urls', existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    op.drop_column('contents', 'media_urls')
