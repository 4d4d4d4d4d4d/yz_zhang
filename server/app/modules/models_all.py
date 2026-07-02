"""汇总导入全部 ORM 模型，供 init_db 建表。新增模块的 models 必须在此登记。"""
from app.modules.account.models import User  # noqa: F401
from app.modules.contract.models import Contract  # noqa: F401
from app.modules.task.models import Application, ProgressLog, Review, Task  # noqa: F401
from app.modules.wallet.models import LedgerEntry, WalletAccount  # noqa: F401
