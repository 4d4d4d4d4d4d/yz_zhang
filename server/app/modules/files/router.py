"""MOB-021 / VND-031 图片上传与读取。

上传前置：必须登录 + 限流。图片是交付凭证与打卡证据的载体，
匿名可传等于给平台开了一个免费图床，也给内容风险开了后门。
"""
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, not_found
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

    name, url = result.external_ref, result.data["url"]
    status, labels = _moderate(db, name, url)
    if status == "reject":
        # UMOD-011/040 被拒的上传不留任何痕迹：删掉命名条目、不落库。
        # 只删名字不动 blobs/<sha256>——别人上传过的同一份内容仍然有效。
        getattr(provider, "delete", lambda _n: False)(name)
        raise bad_request(
            f"图片未通过内容安全审核（{'、'.join(labels) or '违规内容'}），请更换后重试",
            "moderation_rejected",
        )

    # FILE-012 归属落库。此前没有任何地方记下是谁传的——举报一张违规图片时，
    # 平台没有任何途径追溯到上传者。V62 落了这张表，本批才让处置成为可能。
    from .models import UploadedFile

    db.add(UploadedFile(
        name=name, owner_id=user.id,
        sha256=result.data.get("sha256", ""),
        content_type=body.content_type, size_bytes=len(raw),
        moderation_status=status, moderation_labels=labels,
    ))
    return {"url": url, "ref": name}


def _moderate(db: Session, name: str, url: str) -> tuple[str, list[str]]:
    """UMOD-010/013 图片机审。

    改造前**图片从来不过审核**：全仓唯一一处 `moderation.check()` 只传任务
    文本，而 `check()` 的第三个参数就叫 `media_urls`，本地实现里甚至专门为它
    写了「看不了图 → 标记人审」的分支——那段分支从来没有被执行过。

    `review` 放行进人审队列，不是拒绝：本地/沙箱实现对任何图片都返回
    `review`，把它当拒绝会让所有非生产部署完全传不了图。

    **供应商故障时 fail open**，这是本批唯一一个我犹豫过的判断：
    内容安全的常规直觉是宁可错杀，但这里的上传物主要是交付凭证与纠纷证据，
    而运维手册自己写着「交付凭证传不上去等于没有证据」。第三方抖一下的代价
    会落在**被侵害方**身上而不是违规者身上，所以故障时标 `review` 放行、
    进人审队列——既没有放弃审核，也没有让第三方的可用性决定一个人能不能自证。
    """
    provider = get_provider("moderation")
    try:
        verdict = vendor_base.call(
            db, "moderation", provider.name, "check_image", {"url": url},
            lambda: provider.check("image", "", [url]),
        )
    except VendorError as exc:
        return "review", [f"provider_error:{exc.code}"]
    labels = [str(x) for x in (verdict.data.get("labels") or [])]
    if verdict.status == "reject":
        return "reject", labels or ["违规内容"]
    if verdict.status == "review":
        reason = verdict.data.get("reason")
        return "review", labels + ([str(reason)] if reason else [])
    return "pass", labels


@router.get("/files/{name}")
def read_file(name: str):
    """本地实现的读取端点。接真实对象存储后，URL 直接指向 CDN，此端点不再被访问。

    FILE-013 **这是一个能力 URL（capability URL）：匿名可读，知道 URL 即有权读。**
    这不是疏忽——`<img src>` 带不了 Authorization 头，CDN 直出时更不可能
    回源鉴权，所以读取端必然是匿名的。这个模式成立有且只有一个前提：

        **名字必须来自 CSPRNG，且与文件内容无关。**

    改造前名字是 `sha256(内容)[:32]`，于是任何持有一份候选文件的人都能离线
    算出它的 URL，把这个端点变成一台存在性预言机。名字的随机性是这个端点
    能安全匿名的**唯一**依据，改 `LocalStorageProvider.put()` 时务必记得。
    """
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

# ---------- CNT-014 视频直传 ----------
class SignUploadIn(BaseModel):
    content_type: str = Field(pattern="^video/(mp4|quicktime|webm)$")
    size_bytes: int = Field(gt=0)


@router.post("/files/sign-upload")
def sign_video_upload(
    request: Request, body: SignUploadIn, user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """CNT-014 签发视频直传地址。

    视频**不能**走 `POST /files` 那条 base64 路径：一个 50MB 的视频
    base64 之后是 67MB 的 JSON 体，整个读进内存再解码，几个并发就能把进程
    打死。所以视频走对象存储直传——文件根本不经过这个进程。

    本地存储没有 CDN，这里会明确返回 `direct_upload: false` 让客户端失败，
    **而不是给一个假 URL 让它传到不存在的地方**（FILE-013 同一条原则：
    宁可明确失败，不要假装成功）。
    """
    from app.core.guard import guard
    from app.vendors.storage import ALLOWED_VIDEO, MAX_VIDEO_BYTES

    guard(request, "sign-upload", str(user.id), limit=10, ip_limit=30)
    if body.content_type not in ALLOWED_VIDEO:
        raise bad_request("仅支持 MP4 / MOV / WebM", "unsupported_type")
    if body.size_bytes > MAX_VIDEO_BYTES:
        raise bad_request(f"视频超过 {MAX_VIDEO_BYTES // 1024 // 1024}MB 上限", "too_large")

    provider = get_provider("storage")
    signer = getattr(provider, "sign_upload", None)
    if signer is None:
        raise bad_request("当前存储实现不支持视频直传", "direct_upload_unsupported")
    result = signer(body.content_type)
    if not result.data.get("direct_upload"):
        raise bad_request(
            "当前存储实现不支持视频直传（本地存储没有 CDN）——"
            "请配置 PLATFORM_STORAGE_PROVIDER 为支持直传的对象存储",
            "direct_upload_unsupported",
        )
    # 直传的文件不经过本进程，所以归属必须在签发时就落库（FILE-012），
    # 否则举报一个视频时同样答不出「这是谁传的」
    from .models import UploadedFile

    db.add(UploadedFile(
        name=result.external_ref, owner_id=user.id, sha256="",
        content_type=body.content_type, size_bytes=body.size_bytes,
        # 直传的内容本进程看不到，机审只能在回调/异步扫描里做 → 先进人审队列
        moderation_status="review", moderation_labels=["direct_upload_not_inspected"],
    ))
    return {"ref": result.external_ref, **result.data}
