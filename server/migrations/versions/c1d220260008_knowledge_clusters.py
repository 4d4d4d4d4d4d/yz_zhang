"""knowledge clusters: subclass layer between categories and samples

KB-070~076（V134，108 号 spec，设计见 94 号）：知识库只有「大类（人定的）」与
「样本（机器攒的）」两层，中间那层——真正能被复用的那层——是空的。

- `knowledge_clusters`：子类（质心 + 模型名、样本数、结果构成、状态、合并去向）。
- `knowledge_cluster_thresholds`：按大类标定的归并阈值，带标定时的模型名与依据。
- `knowledge_cards` 加 `cluster_id` / `cluster_state` / `cluster_hint`：存量卡片
  `cluster_state = 'pending'`，由归并 job 串行处理——不在迁移里聚类（迁移不调供应商）。

Revision ID: c1d220260008
Revises: c1d220260007
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260008'
down_revision: Union[str, Sequence[str], None] = 'c1d220260007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_clusters',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('label', sa.String(120), nullable=False),
        sa.Column('centroid', sa.JSON(), nullable=False),
        sa.Column('embedding_model', sa.String(40), nullable=False),
        sa.Column('sample_count', sa.Integer(), nullable=False),
        sa.Column('outcome_counts', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('merged_into', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.String(20), nullable=False),
        sa.Column('last_sample_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_knowledge_clusters_category', 'knowledge_clusters', ['category'])
    op.create_index('ix_knowledge_clusters_status', 'knowledge_clusters', ['status'])
    op.create_table(
        'knowledge_cluster_thresholds',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('category', sa.String(50), nullable=False, unique=True),
        sa.Column('tau_merge', sa.Float(), nullable=False),
        sa.Column('tau_near', sa.Float(), nullable=False),
        sa.Column('embedding_model', sa.String(40), nullable=False),
        sa.Column('labeled_pairs', sa.Integer(), nullable=False),
        sa.Column('errors', sa.Integer(), nullable=False),
        sa.Column('calibrated_by', sa.Integer(), nullable=False),
        sa.Column('calibrated_at', sa.DateTime(), nullable=False),
    )
    with op.batch_alter_table('knowledge_cards') as batch:
        batch.add_column(sa.Column('cluster_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('cluster_state', sa.String(12), nullable=False, server_default='pending'))
        batch.add_column(sa.Column('cluster_hint', sa.JSON(), nullable=False, server_default='{}'))
        batch.create_index('ix_knowledge_cards_cluster_id', ['cluster_id'])
        batch.create_index('ix_knowledge_cards_cluster_state', ['cluster_state'])


def downgrade() -> None:
    with op.batch_alter_table('knowledge_cards') as batch:
        batch.drop_index('ix_knowledge_cards_cluster_state')
        batch.drop_index('ix_knowledge_cards_cluster_id')
        batch.drop_column('cluster_hint')
        batch.drop_column('cluster_state')
        batch.drop_column('cluster_id')
    op.drop_table('knowledge_cluster_thresholds')
    op.drop_index('ix_knowledge_clusters_status', 'knowledge_clusters')
    op.drop_index('ix_knowledge_clusters_category', 'knowledge_clusters')
    op.drop_table('knowledge_clusters')
