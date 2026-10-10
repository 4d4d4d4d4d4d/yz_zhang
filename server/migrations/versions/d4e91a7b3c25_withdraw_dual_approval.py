"""PAY-042 大额提现的四眼原则：记下第一次批准是谁、什么时候

第一次批准**不动钱**，只记在这两列上；第二个管理员确认后才放款。
两次必须是不同的人——否则就是同一个人点两次，等于没有这条规则。

`status` 同时放宽到 16 字符：要容纳新状态 `awaiting_second`。

Revision ID: d4e91a7b3c25
Revises: c71fa9e2b840
"""
import sqlalchemy as sa
from alembic import op

revision = "d4e91a7b3c25"
down_revision = "c71fa9e2b840"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 改列必须走 batch（既有约定）
    with op.batch_alter_table("withdraw_requests") as batch:
        batch.add_column(sa.Column("first_approved_by", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("first_approved_at", sa.DateTime(), nullable=True))
        # pending/approved/rejected → 再加 awaiting_second，12 字符不够
        batch.alter_column("status", type_=sa.String(16), existing_type=sa.String(12))


def downgrade() -> None:
    with op.batch_alter_table("withdraw_requests") as batch:
        batch.alter_column("status", type_=sa.String(12), existing_type=sa.String(16))
        batch.drop_column("first_approved_at")
        batch.drop_column("first_approved_by")
