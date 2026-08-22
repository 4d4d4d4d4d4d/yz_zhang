from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

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
    # VND-042 生产环境配置自检：P0 能力仍是模拟实现 / 弱密钥 / SQLite → 拒绝启动
    from app.vendors.registry import startup_check

    startup_check()
    init_db()

    # 领域事件订阅（14 号 spec 第 3 节）
    from app.modules.anchor import service as anchor_service
    from app.modules.decompose import resilience as decompose_resilience
    from app.modules.decompose import service as decompose_service
    from app.modules.im import service as im_service
    from app.modules.knowledge import service as knowledge_service
    from app.modules.matching import events as matching_events
    from app.modules.notification import service as notification_service
    from app.modules.task import events as task_events

    knowledge_service.register_event_handlers()
    decompose_service.register_event_handlers()
    im_service.register_event_handlers()
    notification_service.register_event_handlers()
    matching_events.register_event_handlers()
    task_events.register_event_handlers()
    anchor_service.register_event_handlers()
    decompose_resilience.register_event_handlers()

    from app.modules.analytics import service as analytics_service

    analytics_service.register_event_handlers()

    # 冷启动种子数据（KB 模板与 FAQ、任务类目）
    from app.modules.task import service as task_service

    with SessionLocal() as db:
        knowledge_service.seed(db)
        task_service.seed_categories(db)
        db.commit()

    from app.modules.account.router import router as account_router
    from app.modules.admin.router import router as admin_router
    from app.modules.analytics.router import router as analytics_router
    from app.modules.anchor.router import router as anchor_router
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
    from app.modules.orchestrator.router import router as orchestrator_router
    from app.modules.search.router import router as search_router
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
        search_router,
        anchor_router,
        analytics_router,
        orchestrator_router,
    ):
        app.include_router(router, prefix=settings.API_PREFIX)

    # CONC-013 乐观锁冲突 → 409：并发写同一行时第二个提交在这里被翻译成
    # 明确的业务语义（"请重试"），而不是 500 内部错误
    from sqlalchemy.orm.exc import StaleDataError

    @app.exception_handler(StaleDataError)
    def _stale_data(_request, _exc):
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "code": "concurrent_modification",
                    "message": "数据已被并发修改，请刷新后重试",
                }
            },
        )

    @app.get("/healthz")
    def healthz():
        """DEP-010 存活探针：不查任何外部依赖，永远快速返回。"""
        return {"ok": True}

    @app.get("/readyz")
    def readyz():
        """DEP-011 就绪探针：DB 可读写才导流量，否则 503。"""
        checks: dict[str, str] = {}
        ok = True
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception as exc:  # pragma: no cover - 依赖故障路径
            checks["db"] = f"error: {type(exc).__name__}"
            ok = False
        from app.core.ratelimit import backend_status

        checks["ratelimit"] = backend_status()
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"ready": ok, "env": settings.ENV, "checks": checks},
        )

    return app


app = create_app()
