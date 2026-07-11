"""全局配置。环境变量优先，便于部署与测试覆盖。"""
import os


class Settings:
    APP_NAME = "task-platform"
    API_PREFIX = "/api/v1"
    DATABASE_URL = os.environ.get("PLATFORM_DATABASE_URL", "sqlite:///./data/platform.db")
    JWT_SECRET = os.environ.get("PLATFORM_JWT_SECRET", "dev-secret-change-me")
    JWT_ALG = "HS256"
    JWT_EXPIRE_MINUTES = int(os.environ.get("PLATFORM_JWT_EXPIRE_MINUTES", "43200"))
    # 开发/测试环境短信验证码固定值（ACC-001 的模拟实现，生产接短信服务商）
    DEV_SMS_CODE = "123456"
    # 平台抽佣（SC-009），万分比，后台可配的简化版
    PLATFORM_FEE_BPS = int(os.environ.get("PLATFORM_FEE_BPS", "800"))  # 8%
    # 验收超时自动通过天数（TASK-031）
    AUTO_ACCEPT_DAYS = int(os.environ.get("PLATFORM_AUTO_ACCEPT_DAYS", "3"))
    # SC-012 签署有效期：成交后 N 天未完成双签自动作废（业界 offer 有效期惯例），
    # 释放被冻结的执行者保证金，避免资金无限期卡死
    SIGN_EXPIRE_DAYS = int(os.environ.get("PLATFORM_SIGN_EXPIRE_DAYS", "3"))
    # CRED-002 双盲互评窗口（业界惯例 14 天）：窗口内提交，双方都评完
    # 或窗口到期才互相/对外可见；到期后不可再补评
    REVIEW_WINDOW_DAYS = int(os.environ.get("PLATFORM_REVIEW_WINDOW_DAYS", "14"))
    # TASK-011 执行者并发接单上限（零工平台惯例）：防过度接单导致履约违约
    MAX_ACTIVE_TASKS = int(os.environ.get("PLATFORM_MAX_ACTIVE_TASKS", "5"))
    # 到场打卡允许误差（米，GEO-020）
    CHECKIN_RADIUS_M = int(os.environ.get("PLATFORM_CHECKIN_RADIUS_M", "500"))
    # 陌生人私聊未获回复前的消息上限（IM-005）
    STRANGER_MSG_LIMIT = 5


settings = Settings()
