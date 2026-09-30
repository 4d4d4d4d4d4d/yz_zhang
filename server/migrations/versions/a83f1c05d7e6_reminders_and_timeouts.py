"""TEAM-063 / NTF-063 / TEAM-055 / PAY-044 催办、临期与预警的四个状态位

四条都是「闹钟只响一次」，所以四条都要记「响过没有 / 上次什么时候响的」：

- `tasks.acceptance_reminded`：自动放款前那条提醒发过没有（只发一次）
- `team_spend_requests.reminded_at`：上次催办时间（催办按间隔重复）
- `teams.pool_warned_month`：本月预警过没有（记月份而不是布尔，
  自然月重置不需要另一个 job 去清）
- `withdraw_requests.review_reminded_at`：上次催办管理员的时间

Revision ID: a83f1c05d7e6
Revises: d4e91a7b3c25
"""
import sqlalchemy as sa
from alembic import op

revision = "a83f1c05d7e6"
down_revision = "d4e91a7b3c25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 改列必须走 batch（既有约定）
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("acceptance_reminded", sa.Boolean(),
                                   nullable=False, server_default=sa.false()))
    with op.batch_alter_table("team_spend_requests") as batch:
        batch.add_column(sa.Column("reminded_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("teams") as batch:
        batch.add_column(sa.Column("pool_warned_month", sa.String(7),
                                   nullable=False, server_default=""))
    with op.batch_alter_table("withdraw_requests") as batch:
        batch.add_column(sa.Column("review_reminded_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("withdraw_requests") as batch:
        batch.drop_column("review_reminded_at")
    with op.batch_alter_table("teams") as batch:
        batch.drop_column("pool_warned_month")
    with op.batch_alter_table("team_spend_requests") as batch:
        batch.drop_column("reminded_at")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("acceptance_reminded")
