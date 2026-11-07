"""personal workbench

PWB-001~012（V141，116 号 spec）：个人工作台——项目、个人任务（含一层清单）、进展记录、
助手记忆、例行任务与运行记录。全部是个人私有数据，与平台任务（tasks）分表，通过 linked_task_id 关联。

Revision ID: c1d220260011
Revises: c1d220260010
Create Date: 2026-10-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c1d220260011'
down_revision: Union[str, Sequence[str], None] = 'c1d220260010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wb_projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('color', sa.String(length=16), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.Column('sort', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_wb_projects_owner_id', 'wb_projects', ['owner_id'])
    op.create_table(
        'wb_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=40), nullable=False),
        sa.Column('due_at', sa.DateTime(), nullable=True),
        sa.Column('remind_at', sa.DateTime(), nullable=True),
        sa.Column('reminded_at', sa.DateTime(), nullable=True),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=False),
        sa.Column('linked_task_id', sa.Integer(), nullable=True),
        sa.Column('sort', sa.Integer(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ('owner_id', 'project_id', 'parent_id', 'due_at', 'remind_at'):
        op.create_index(f'ix_wb_items_{col}', 'wb_items', [col])
    op.create_table(
        'wb_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_wb_logs_item_id', 'wb_logs', ['item_id'])
    op.create_index('ix_wb_logs_owner_id', 'wb_logs', ['owner_id'])
    op.create_table(
        'wb_memories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_wb_memories_owner_id', 'wb_memories', ['owner_id'])
    op.create_table(
        'wb_routines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('freq', sa.String(length=16), nullable=False),
        sa.Column('time_of_day', sa.String(length=5), nullable=False),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('monthday', sa.Integer(), nullable=False),
        sa.Column('run_at', sa.DateTime(), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_status', sa.String(length=16), nullable=False),
        sa.Column('failures', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_wb_routines_owner_id', 'wb_routines', ['owner_id'])
    op.create_index('ix_wb_routines_next_run_at', 'wb_routines', ['next_run_at'])
    op.create_table(
        'wb_routine_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('routine_id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('output', sa.Text(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_wb_routine_runs_routine_id', 'wb_routine_runs', ['routine_id'])
    op.create_index('ix_wb_routine_runs_owner_id', 'wb_routine_runs', ['owner_id'])


def downgrade() -> None:
    for t in ('wb_routine_runs', 'wb_routines', 'wb_memories', 'wb_logs', 'wb_items', 'wb_projects'):
        op.drop_table(t)
