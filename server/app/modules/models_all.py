"""汇总导入全部 ORM 模型，供 init_db 建表。新增模块的 models 必须在此登记。"""
from app.modules.account.models import Block, LoginSession, User  # noqa: F401
from app.modules.anchor.models import AnchorEntry  # noqa: F401
from app.modules.circle.models import Circle, CircleMember  # noqa: F401
from app.modules.content.models import Comment, Content, Follow, Like  # noqa: F401
from app.modules.contract.models import ChangeOrder, Contract, Milestone  # noqa: F401
from app.modules.decompose.models import Decomposition  # noqa: F401
from app.modules.admin.models import Report  # noqa: F401
from app.modules.dispute.models import Dispute  # noqa: F401
from app.modules.matching.models import Invitation, MatchingConfig, Subscription  # noqa: F401
from app.modules.support.models import NotificationPref, Ticket  # noqa: F401
from app.modules.im.models import Conversation, Message  # noqa: F401
from app.modules.notification.models import Notification  # noqa: F401
from app.modules.knowledge.models import (  # noqa: F401
    DecompositionTemplate,
    FaqEntry,
    KnowledgeCard,
)
from app.modules.task.models import (  # noqa: F401
    Application,
    Category,
    City,
    ProgressLog,
    Review,
    Task,
)
from app.modules.wallet.models import LedgerEntry, WalletAccount  # noqa: F401
