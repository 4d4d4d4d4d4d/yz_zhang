"""汇总导入全部 ORM 模型，供 init_db 建表。新增模块的 models 必须在此登记。"""
from app.core.idempotency import IdempotencyRecord  # noqa: F401
from app.core.models_infra import JobLock  # noqa: F401
from app.vendors.models import PaymentOrder, SmsCode, VendorCall  # noqa: F401
from app.modules.account.models import Block, LoginSession, User  # noqa: F401
from app.modules.analytics.models import AnalyticsEvent, SearchQuery  # noqa: F401
from app.modules.anchor.models import AnchorEntry, AnchorReceipt  # noqa: F401
from app.modules.circle.models import Circle, CircleMember  # noqa: F401
from app.modules.content.models import Comment, Content, Follow, Like  # noqa: F401
from app.modules.contract.models import (  # noqa: F401
    ChangeOrder,
    Contract,
    ContractSignature,
    Milestone,
)
from app.modules.decompose.models import Decomposition  # noqa: F401
from app.modules.admin.models import Report  # noqa: F401
from app.modules.dispute.models import Dispute  # noqa: F401
from app.modules.finance.models import SettlementOrder, SettlementSplit  # noqa: F401
from app.modules.growth.models import Campaign, Coupon, ReferralReward, UserCoupon  # noqa: F401
from app.modules.legal.consent import UserConsent  # noqa: F401
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
from app.modules.orchestrator.models import (  # noqa: F401
    Mission,
    MissionEvent,
    MissionStep,
    StepReview,
)
