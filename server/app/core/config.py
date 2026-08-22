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
    # TASK-033 验收驳回上限：超过后不得再单方驳回，须验收或走仲裁（防无限返工变相欠薪）
    MAX_REJECT_ROUNDS = int(os.environ.get("PLATFORM_MAX_REJECT_ROUNDS", "3"))
    # DSP-009 纠纷处理 SLA：开立超 N 天未结案自动升级进人审队列（防托管资金无限期冻结）
    DISPUTE_SLA_DAYS = int(os.environ.get("PLATFORM_DISPUTE_SLA_DAYS", "7"))
    # DSP-010 申诉窗口：仲裁结案后 N 天内可申诉，逾期裁决终局
    APPEAL_WINDOW_DAYS = int(os.environ.get("PLATFORM_APPEAL_WINDOW_DAYS", "7"))
    # ORC-004 编排规划预留：规划阶段只用上限的 (1-预留)，其余留给失败重试，
    # 否则首轮就把预算用满、修复步永远无钱可发（agent 必须自带重试余量）
    ORC_PLAN_RESERVE_BPS = int(os.environ.get("PLATFORM_ORC_PLAN_RESERVE_BPS", "3000"))
    # DSP-005 答辩期（小时）：被诉方未答辩且答辩期未过时不得裁决（两造兼听），
    # 逾期未答辩可缺席裁决，避免一方不出面就拖死流程
    DISPUTE_RESPONSE_HOURS = int(os.environ.get("PLATFORM_DISPUTE_RESPONSE_HOURS", "48"))
    # PAY-007 提现风控（业界惯例）：单日累计限额；大额提现冻结进人审队列
    WITHDRAW_DAILY_LIMIT_CENTS = int(os.environ.get("PLATFORM_WITHDRAW_DAILY_LIMIT_CENTS", "5000000"))  # ¥5万/日
    LARGE_WITHDRAW_CENTS = int(os.environ.get("PLATFORM_LARGE_WITHDRAW_CENTS", "1000000"))  # ≥¥1万人审
    # 到场打卡允许误差（米，GEO-020）
    CHECKIN_RADIUS_M = int(os.environ.get("PLATFORM_CHECKIN_RADIUS_M", "500"))
    # 陌生人私聊未获回复前的消息上限（IM-005）
    STRANGER_MSG_LIMIT = 5
    # OPS-011 内部定时任务共享密钥：cron 端点必须携带 X-Job-Token（生产改强随机值）
    JOB_TOKEN = os.environ.get("PLATFORM_JOB_TOKEN", "dev-job-token-change-me")
    # ── CONC 并发与生产化（18 号 spec）──────────────────────────────
    # 运行环境：dev/test/prod。prod 下启动自检更严格（弱密钥、mock 供应商拒绝启动）
    ENV = os.environ.get("PLATFORM_ENV", "dev")
    # CONC-002 连接池（仅非 SQLite 生效；SQLite 不支持池参数）
    DB_POOL_SIZE = int(os.environ.get("PLATFORM_DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW = int(os.environ.get("PLATFORM_DB_MAX_OVERFLOW", "20"))
    DB_POOL_RECYCLE = int(os.environ.get("PLATFORM_DB_POOL_RECYCLE", "1800"))
    DB_POOL_PRE_PING = os.environ.get("PLATFORM_DB_POOL_PRE_PING", "1") != "0"
    # CONC-003 SQLite 本地并发：WAL + busy_timeout（毫秒）
    SQLITE_BUSY_TIMEOUT_MS = int(os.environ.get("PLATFORM_SQLITE_BUSY_TIMEOUT_MS", "5000"))
    # CONC-021 分布式限流后端：配置了 Redis 就用 Redis，否则进程内内存实现
    REDIS_URL = os.environ.get("PLATFORM_REDIS_URL", "")
    # CONC-020 Redis 连续失败达阈值后冷却降级为内存实现（可用性优先于严格限流）
    RATELIMIT_FAIL_THRESHOLD = int(os.environ.get("PLATFORM_RATELIMIT_FAIL_THRESHOLD", "3"))
    RATELIMIT_COOLDOWN_SECONDS = int(os.environ.get("PLATFORM_RATELIMIT_COOLDOWN_SECONDS", "30"))
    # CONC-041 定时任务执行锁 TTL（秒）：持锁进程崩溃后超时可被抢占
    JOB_LOCK_TTL_SECONDS = int(os.environ.get("PLATFORM_JOB_LOCK_TTL_SECONDS", "300"))


settings = Settings()
