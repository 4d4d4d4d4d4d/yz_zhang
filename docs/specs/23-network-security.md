# 23 · 分布式部署与抗攻击（SEC）

> 现状：V44 已给出 Postgres + Redis + 多副本 api + 单副本 worker + Nginx 的生产栈，
> 但**边界防护基本为零**：无 TLS、Nginx 无限流、应用限流只有 7 个调用点且
> **按账号维度限**（换个手机号就绕开）、无 WAF/验证码/IP 封禁。
> 本 spec 把「能部署」补成「能扛住恶意流量」。

## 23.A 传输与边界（P0）

- **SEC-001** Nginx 强制 TLS：HTTP 301 跳 HTTPS、HSTS、禁用 TLS<1.2、
  OCSP stapling；证书由 ACME 自动续期（证书与域名需用户提供，配置模板随仓库给出）。
- **SEC-002** 安全响应头：`X-Content-Type-Options`、`X-Frame-Options: DENY`、
  `Referrer-Policy`、`Content-Security-Policy`、`Permissions-Policy`。
- **SEC-003** 隐藏实现细节：关闭 `server_tokens`、移除 `X-Powered-By`、
  生产关闭 `/docs` 与 `/openapi.json`（`PLATFORM_ENV=prod` 时不挂载）。
- **SEC-004** 请求体大小上限与超时：`client_max_body_size`、
  `client_body_timeout`、`send_timeout`，防慢速攻击（Slowloris）。

## 23.B 多层限流（P0）

现有限流是**账号维度**，对「批量注册」「代理池刷接口」完全无效。补三层：

- **SEC-010** 网关层 IP 限流：Nginx `limit_req_zone` 按 `$binary_remote_addr`，
  登录/注册/发码类路径单独更严的 zone；`limit_conn` 限并发连接数。
- **SEC-011** 应用层 **IP + 账号双维度**：`ratelimit.check` 增加 IP key，
  任一维度超限即拒；`X-Forwarded-For` 只信任反代注入的最后一跳
  （**不能直接取 XFF 首个 IP**——那是客户端可伪造的）。
- **SEC-012** 全局兜底限流中间件：所有写操作（POST/PUT/DELETE）按 IP 限速，
  避免遗漏新增端点（新端点默认受保护，而不是默认裸奔）。
- **SEC-013** 资金类端点独立更严的配额：托管/放款/提现/核销券。

## 23.C 异常行为识别与处置（P0）

- **SEC-020** 失败计数与自动封禁：同一 IP 连续认证失败达阈值 → 临时封禁
  （封禁写 Redis/DB，多副本共享）；封禁可被管理员解除。
- **SEC-021** 人机验证挂钩：触发风控阈值后要求验证码
  （`CaptchaProvider` 抽象 + Mock 直通，接第三方只改环境变量）。
- **SEC-022** 可疑请求特征：无 UA、异常高频跨账号、同一设备指纹多账号，
  落 `SecurityEvent` 表并进风控队列。
- **SEC-023** 管理端安全看板：近期封禁、限流命中 Top、认证失败趋势。

## 23.D 应用层攻击面（P0）

- **SEC-030** CORS 生产白名单（V44 已可配，本条确保 prod 自检拒绝 `*`）。
- **SEC-031** 越权复查：所有资源级读写以「当事人/管理员」为准，
  新增端点必须进越权测试清单。
- **SEC-032** 输入边界：所有字符串字段有长度上限、所有列表有 `max_length`、
  分页 `limit` 有硬上限（防内存放大攻击）。
- **SEC-033** 上传防护（已有魔数校验/大小上限/限流）补充：
  存储目录不可执行、响应带 `Content-Disposition` 与
  `X-Content-Type-Options: nosniff`，杜绝上传图片被当脚本执行。

## 23.E 多副本一致性（P1）

- **SEC-040** 事件总线跨副本：`InProcessBus` 之外提供 `RedisBus`
  （发布/订阅），把「后继子任务自动发布」这类**必须只执行一次**的事件
  改为带幂等键的消费；幂等可重放的事件（通知、经验入库）保持进程内即可。
- **SEC-041** 会话与令牌：令牌已绑定可吊销的 `LoginSession`，
  补充「异地/异设备登录提醒」与「一键下线全部设备」。

## 23.F 验证（P0）

- **SEC-050** IP 限流测试：同 IP 换账号仍被拦。
- **SEC-051** XFF 伪造测试：伪造 `X-Forwarded-For` 不能绕过 IP 限流。
- **SEC-052** 自动封禁测试：连续失败触发封禁，封禁期内直接拒绝。
- **SEC-053** 生产自检测试：prod 下 CORS 为 `*` 或 `/docs` 暴露则启动失败。
- **SEC-054** 安全响应头测试：关键头存在且取值正确。

## 验收标准

- 换账号不换 IP、换 IP 不换账号，两种刷法都被挡；
- 生产环境不暴露 API 文档、不允许通配 CORS；
- 上传的图片无论如何构造都不可能被当作脚本执行。
