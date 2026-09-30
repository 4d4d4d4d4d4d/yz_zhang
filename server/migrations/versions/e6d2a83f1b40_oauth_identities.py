"""account: third-party login identities (ACC-003)

spec 的备注写着「App 端 Apple 登录为上架合规必需」——App Store 的规则是
只要提供了任何第三方登录，就必须同时提供 Sign in with Apple。
所以这不是体验加分项，是上架前置条件。

Revision ID: e6d2a83f1b40
Revises: d4b1e7c05a92
Create Date: 2026-09-16 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6d2a83f1b40'
down_revision: Union[str, Sequence[str], None] = 'd4b1e7c05a92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'oauth_identities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=16), nullable=False),
        # subject 是第三方给的稳定标识，不是邮箱也不是手机号——
        # 邮箱会变，Apple 还允许用户隐藏真实邮箱
        sa.Column('subject', sa.String(length=191), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        # 一个第三方账号只能绑一个本站账号，否则「用微信登录」会不确定登进哪个
        sa.UniqueConstraint('provider', 'subject'),
    )
    op.create_index('ix_oauth_identities_provider', 'oauth_identities', ['provider'])
    op.create_index('ix_oauth_identities_subject', 'oauth_identities', ['subject'])
    op.create_index('ix_oauth_identities_user_id', 'oauth_identities', ['user_id'])


def downgrade() -> None:
    for idx in ('user_id', 'subject', 'provider'):
        op.drop_index(f'ix_oauth_identities_{idx}', table_name='oauth_identities')
    op.drop_table('oauth_identities')
