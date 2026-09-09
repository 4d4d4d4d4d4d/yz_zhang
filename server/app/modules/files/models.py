"""FILE-012 上传归属。

改造前上传要求登录，但**没有任何地方记下是谁传的**：
`VendorCall` 只记 kind / provider / operation / request_digest，不含用户。

所以举报一张违规图片、或内容安全供应商回报一个问题对象时，平台没有任何
途径追溯到上传者。一个有举报流程、有 `MODERATION_PROVIDER`、要对内容
负责的平台，连归属都不记，处置就无从谈起。
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    # FILE-010 随机令牌，与内容无关：读取端点是匿名的（CDN 直出时只能匿名），
    # 靠的是「URL 不可猜」这个能力 URL 前提，而内容哈希对持有内容的人是公开的
    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    # 内容哈希留在这里而不是留在名字里：去重与排查靠它，可达性不靠它
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    content_type: Mapped[str] = mapped_column(String(32))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
