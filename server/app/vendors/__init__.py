"""外部供应商接入抽象层（19 号 spec / VND）。

业务模块只 import 本包：`from app.vendors.registry import get_provider`。
任何供应商 SDK 都不得出现在 `app/modules/` 下。
"""
