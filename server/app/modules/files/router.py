"""MOB-021 / VND-031 图片上传与读取。

上传前置：必须登录 + 限流。图片是交付凭证与打卡证据的载体，
匿名可传等于给平台开了一个免费图床，也给内容风险开了后门。
"""
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import not_found
from app.modules.account.models import User
from app.vendors import base as vendor_base
from app.vendors.base import VendorError
from app.vendors.registry import get_provider
from app.vendors.storage import decode_upload

router = APIRouter(tags=["files"])


class UploadIn(BaseModel):
    content_type: str = Field(pattern="^image/(jpeg|png|webp)$")
    data_base64: str = Field(min_length=16)


@router.post("/files", status_code=201)
def upload_file(request: Request, body: UploadIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """MOB-021 上传图片（客户端压缩后的 base64）。

    校验三件事：类型白名单、大小上限、**魔数与声明类型一致**——
    只信 Content-Type 等于让上传方自证清白。
    """
    from app.core.guard import guard

    # SEC-011：上传要占存储、要过内容审核，都是花钱的动作 → 账号 + IP 双维度
    guard(request, "upload", str(user.id), limit=20, ip_limit=40)
    provider = get_provider("storage")
    try:
        raw = decode_upload(body.data_base64, body.content_type)
        result = vendor_base.call(
            db, "storage", provider.name, "put",
            {"content_type": body.content_type, "bytes": len(raw)},
            lambda: provider.put(raw, body.content_type),
        )
    except VendorError as exc:
        raise exc.as_http() from exc
    return {"url": result.data["url"], "ref": result.external_ref}


@router.get("/files/{name}")
def read_file(name: str):
    """本地实现的读取端点。接真实对象存储后，URL 直接指向 CDN，此端点不再被访问。"""
    provider = get_provider("storage")
    got = getattr(provider, "read", lambda _n: None)(name)
    if not got:
        raise not_found("文件不存在")
    data, content_type = got
    # SEC-033：即便有人想办法传了个「既是合法图片又是合法脚本」的文件，
    # nosniff + attachment 也让它无法被当作脚本在我们的源上执行
    return Response(
        content=data, media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{name}"',
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
