"""legal: user consent records and adult flag

Revision ID: 8c31a0be47f2
Revises: 2ae4a0fbafd7
Create Date: 2026-08-25 09:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c31a0be47f2'
down_revision: Union[str, Sequence[str], None] = '2ae4a0fbafd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_consents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('scope', sa.String(length=24), nullable=False),
        sa.Column('version', sa.String(length=24), nullable=False),
        sa.Column('notice', sa.Text(), nullable=False, server_default=''),
        sa.Column('granted_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        # 同一版本同一项只留一条有效同意；撤回记录（revoked_at 非空）不受此约束限制，
        # 因为 SQL 里 NULL 互不相等——这正是「可以撤回多次、但同时只有一条有效」想要的语义
        sa.UniqueConstraint('user_id', 'scope', 'version', 'revoked_at',
                            name='uq_consent_user_scope_version'),
    )
    op.create_index(op.f('ix_user_consents_user_id'), 'user_consents', ['user_id'])
    op.create_index(op.f('ix_user_consents_scope'), 'user_consents', ['scope'])

    # 存量用户按未成年处理会把他们全部挡在接单外，按成年处理又是无凭据的放行。
    # 取后者并留痕：这个标记只在**下一次实名认证**时才被写成可信值，
    # 存量用户的 True 仅代表「历史上通过了当时的实名流程」。
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_adult', sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('is_adult')
    op.drop_index(op.f('ix_user_consents_scope'), table_name='user_consents')
    op.drop_index(op.f('ix_user_consents_user_id'), table_name='user_consents')
    op.drop_table('user_consents')
