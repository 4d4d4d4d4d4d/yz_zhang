from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.db import init_db


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    init_db()

    from app.modules.account.router import router as account_router
    from app.modules.contract.router import router as contract_router
    from app.modules.task.router import router as task_router
    from app.modules.wallet.router import router as wallet_router

    for router in (account_router, wallet_router, task_router, contract_router):
        app.include_router(router, prefix=settings.API_PREFIX)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    return app


app = create_app()
