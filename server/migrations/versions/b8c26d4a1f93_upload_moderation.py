"""files: upload moderation status (UMOD-014)

改造前图片从来不过审核——全仓唯一一处 moderation.check() 只传任务文本，
而本地实现里专门为 media_urls 写的「看不了图 → 标记人审」分支从未被执行过。

Revision ID: b8c26d4a1f93
Revises: a71e3f9d2b46
Create Date: 2026-09-16 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c26d4a1f93'
down_revision: Union[str, Sequence[str], None] = 'a71e3f9d2b46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('uploaded_files', sa.Column(
        'moderation_status', sa.String(length=12), nullable=False, server_default='pass'))
    op.add_column('uploaded_files', sa.Column(
        'moderation_labels', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('uploaded_files', 'moderation_labels')
    op.drop_column('uploaded_files', 'moderation_status')
