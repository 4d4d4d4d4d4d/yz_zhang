"""QUEUE-012 超时告知过谁：一张表，而不是六个队列各加一列

「已经告知过提交方」这个状态存在队列之外：六个人审队列分别落在六张表里，
给每张表加一个 `sla_notified_at` 是六次迁移、六处容易漏的地方。
`item_key` 是字符串——上传队列的主键是文件名，不是整数。

Revision ID: b5c27e91f4a8
Revises: a83f1c05d7e6
"""
import sqlalchemy as sa
from alembic import op

revision = "b5c27e91f4a8"
down_revision = "a83f1c05d7e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "queue_sla_notices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("queue_key", sa.String(24), nullable=False, index=True),
        sa.Column("item_key", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("queue_sla_notices")
