2026-10-17：新增视觉与APK边界见 [VISION-ACCEPTANCE.md](VISION-ACCEPTANCE.md) 和 [Android说明](../android/README.md)。图片在选取端本地缩放后发送到手机本地服务，原图不落库；回答文本加密保存。网页在Mac打开时，所选图片来自Mac，经ADB转发到手机。下文描述ADB开发版原有边界。

# 本地资料库隐私边界

这是 ADB shell 开发版的应用层记录加密，不是已完成安全审计的 Android 产品。

- SQLite 位于手机 `/data/local/tmp/qwen-phone/private/vault.db`。画像、笔记、历史对话、摘要以及会话索引均先加密再写入 SQLite。
- PBKDF2-HMAC-SHA256，600,000 次迭代，随机 16 字节盐，派生 64 字节后分为 AES 与索引 HMAC 的两个 256 位密钥。
- 每次写入生成独立随机 96 位 nonce；AES-256-GCM，128 位认证标签；版本和记录 HMAC ID 作为 AAD。记录 ID 使用 HMAC，避免以明文暴露笔记名或字段类型。
- SQLite schema、盐、密文大小、记录数量和文件访问时序仍可观察。不是 SQLCipher 全库/文件头加密。临时存储采用内存模式，rollback journal 采用 DELETE 模式以保留崩溃恢复能力；数据库与日志中的记录值均为密文。开启 SQLite secure_delete，但不承诺对闪存、历史备份或文件系统快照的取证级擦除。
- 口令不持久化，解锁密钥仅留在进程内。15 分钟无 API 操作自动锁定；重启后必须解锁。没有忘记口令恢复后门。浏览器 bearer 凭证仅存在当前页面内存，不使用 localStorage/cookie 保存。
- 锁定使现有 token/任务失效、清空待执行任务、取消推理连接，并安排清除 llama slot 的 prompt cache。Java String、GC、驱动缓存与物理内存不提供可验证的即时全量擦除保证；解锁时资料必然进入内存和模型上下文。`cache-ram=0` 禁用跨请求 RAM prompt cache；不配置 slot 磁盘保存。
- 手动画像由用户编辑；勾选收集后可产生四类明确风格的候选偏好，原话和来源加密保存，确认后才参与回答。任务记忆按会话隔离；模型没有画像确认工具。删除条目后保存即更新。模型生成的对话摘要只作上下文资料，不变成用户确认的画像。
- 网页检索只发送界面显示并批准的 query 到 Bing；没有传递整段对话或画像。工具内容视作不可信资料。允许前应检查 query；不能依赖提示词保证模型永远不会提出包含私人内容的查询。工具返回的是搜索摘要，不是完整网页阅读。
- HTTP 只监听手机 loopback，通过 ADB 转发；校验 Host/Origin，拒绝跨站 JSON 请求；私有接口需 bearer。loopback HTTP 不等于 TLS，也不隔离同 UID 的恶意进程。不要把端口公开到局域网或公网。
- 当前服务与其他 ADB shell 程序共享 UID。权限 0700/0600 和加密主要保护锁定状态下的离线数据，不防御已授权 ADB、root、被控制的宿主机或解锁时同 UID 的恶意程序。
- 后续产品化应迁移独立 APK UID、前台服务、Android Keystore（可用时硬件保护）与设备认证。当前未声称使用硬件 Keystore；浏览器口令不应被嵌入脚本或传给开发者。
- 原 v1 演示笔记目录 `notes/` 是旧的明文目录；v2 不读取它、不把新笔记写入它。未擅自删除或迁移现有文件。

设备测试：错误口令、认证标签篡改、重开数据库读取、已知测试明文扫描均通过；API 还验证未认证访问、外站 Origin、锁定后访问、手动画像删除。测试使用隔离数据库，不预设正式用户口令。上述验证不是完整渗透测试。

参考：[Android cryptography](https://developer.android.com/privacy-and-security/cryptography)。
