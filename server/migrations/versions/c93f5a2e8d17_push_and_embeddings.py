"""notification: device tokens; knowledge: vector index (NTF-002 / KB-011)

补的是两条「注释里写了要做、但一直没做」的降级实现：
- 站内信 → 真正的推送通道（设备令牌是它的收件地址）
- 关键词匹配 → 向量检索管线（embedding_model 一起存，换模型才能增量重建）

Revision ID: c93f5a2e8d17
Revises: b8c26d4a1f93
Create Date: 2026-09-16 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c93f5a2e8d17'
down_revision: Union[str, Sequence[str], None] = 'b8c26d4a1f93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'device_tokens',
        # 令牌即主键：App 每次启动都会注册，重复行的后果是同一条通知推四遍
        sa.Column('token', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('platform', sa.String(length=10), nullable=False, server_default='ios'),
        sa.Column('revoked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('token'),
    )
    op.create_index('ix_device_tokens_user_id', 'device_tokens', ['user_id'])

    for table in ('knowledge_cards', 'faq_entries'):
        op.add_column(table, sa.Column('embedding', sa.JSON(), nullable=True))
        op.add_column(table, sa.Column(
            'embedding_model', sa.String(length=40), nullable=False, server_default=''))
        op.execute(f"UPDATE {table} SET embedding = '[]' WHERE embedding IS NULL")
        # batch 模式：SQLite 不支持 ALTER COLUMN，Postgres 上就是普通 ALTER
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column('embedding', existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    for table in ('faq_entries', 'knowledge_cards'):
        op.drop_column(table, 'embedding_model')
        op.drop_column(table, 'embedding')
    op.drop_index('ix_device_tokens_user_id', table_name='device_tokens')
    op.drop_table('device_tokens')
