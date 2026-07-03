from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import SessionLocal, init_db


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    init_db()

    # 领域事件订阅（14 号 spec 第 3 节）
    from app.modules.decompose import service as decompose_service
    from app.modules.im import service as im_service
    from app.modules.knowledge import service as knowledge_service
    from app.modules.matching import events as matching_events
    from app.modules.notification import service as notification_service

    knowledge_service.register_event_handlers()
    decompose_service.register_event_handlers()
    im_service.register_event_handlers()
    notification_service.register_event_handlers()
    matching_events.register_event_handlers()

    # 冷启动种子数据（KB 模板与 FAQ）
    with SessionLocal() as db:
        knowledge_service.seed(db)
        db.commit()

    from app.modules.account.router import router as account_router
    from app.modules.admin.router import router as admin_router
    from app.modules.circle.router import router as circle_router
    from app.modules.legal.router import router as legal_router
    from app.modules.matching.router import router as matching_router
    from app.modules.content.router import router as content_router
    from app.modules.contract.router import router as contract_router
    from app.modules.decompose.router import router as decompose_router
    from app.modules.dispute.router import router as dispute_router
    from app.modules.im.router import router as im_router
    from app.modules.knowledge.router import router as knowledge_router
    from app.modules.notification.router import router as notification_router
    from app.modules.support.router import router as support_router
    from app.modules.task.router import router as task_router
    from app.modules.wallet.router import router as wallet_router

    for router in (
        account_router,
        wallet_router,
        task_router,
        contract_router,
        decompose_router,
        knowledge_router,
        im_router,
        dispute_router,
        notification_router,
        support_router,
        content_router,
        circle_router,
        matching_router,
        legal_router,
        admin_router,
    ):
        app.include_router(router, prefix=settings.API_PREFIX)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app


app = create_app()
