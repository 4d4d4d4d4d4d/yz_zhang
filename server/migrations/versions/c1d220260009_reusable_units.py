"""reusable units and their invocations

KB-080~089 / AGT-080~083（V135，109 号 spec，设计见 95 号）：经验从「拼进提示词」
变成可被调用、可计量、可验证的单元。

- `reusable_units`：从子类蒸馏出来的单元（价格提示 / 验收清单 / 分解流程 / 可执行工具），
  带来源、适用与排除条件、验证结果、复用与训练两个独立授权位、工具声明。
- `unit_invocations`：每次调用留痕与结果回流（闭环 / 返工 / 失败），受益贡献者清单，
  草稿是否被丢弃、来源是否已撤回。

Revision ID: c1d220260009
Revises: c1d220260008
Create Date: 2026-10-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260009'
down_revision: Union[str, Sequence[str], None] = 'c1d220260008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reusable_units',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cluster_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('title', sa.String(120), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('applicability', sa.JSON(), nullable=False),
        sa.Column('sample_ids', sa.JSON(), nullable=False),
        sa.Column('validation', sa.JSON(), nullable=False),
        sa.Column('scope', sa.String(12), nullable=False),
        sa.Column('reuse_license', sa.Boolean(), nullable=False),
        sa.Column('train_license', sa.Boolean(), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('est_cost_cents', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(14), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_reusable_units_cluster_id', 'reusable_units', ['cluster_id'])
    op.create_index('ix_reusable_units_kind', 'reusable_units', ['kind'])
    op.create_index('ix_reusable_units_status', 'reusable_units', ['status'])
    op.create_table(
        'unit_invocations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('unit_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('scenario', sa.String(24), nullable=False),
        sa.Column('caller_id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('input_summary', sa.String(300), nullable=False),
        sa.Column('output', sa.JSON(), nullable=False),
        sa.Column('cost_cents', sa.Integer(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('outcome', sa.String(10), nullable=False),
        sa.Column('beneficiaries', sa.JSON(), nullable=False),
        sa.Column('draft', sa.Boolean(), nullable=False),
        sa.Column('discarded', sa.Boolean(), nullable=False),
        sa.Column('source_revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_unit_invocations_unit_id', 'unit_invocations', ['unit_id'])
    op.create_index('ix_unit_invocations_caller_id', 'unit_invocations', ['caller_id'])
    op.create_index('ix_unit_invocations_task_id', 'unit_invocations', ['task_id'])
    op.create_index('ix_unit_invocations_outcome', 'unit_invocations', ['outcome'])


def downgrade() -> None:
    for ix in ('ix_unit_invocations_outcome', 'ix_unit_invocations_task_id',
               'ix_unit_invocations_caller_id', 'ix_unit_invocations_unit_id'):
        op.drop_index(ix, 'unit_invocations')
    op.drop_table('unit_invocations')
    for ix in ('ix_reusable_units_status', 'ix_reusable_units_kind', 'ix_reusable_units_cluster_id'):
        op.drop_index(ix, 'reusable_units')
    op.drop_table('reusable_units')
