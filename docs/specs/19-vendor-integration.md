# 19 · 外部供应商接入抽象层（VND）

> 现状：支付/短信/实名/内容审核全是**平台内模拟实现**，散落在各模块里。
> 上线必须换成持牌供应商，但**不能因此改业务代码**。
> 本 spec 定义统一的 Provider 抽象：业务只依赖接口，供应商靠配置切换，
> 缺省走 Mock（开发/CI 不需要任何密钥）。

## 19.A 通用 Provider 框架（P0）

- **VND-001** 统一注册表 `app/vendors/registry.py`：
  `get_provider(kind)` 按 `PLATFORM_<KIND>_PROVIDER` 配置返回实现，
  未配置或配置为 `mock` 时返回 Mock 实现。
- **VND-002** 所有 Provider 抛出的失败统一收敛为 `VendorError(code, message, retryable)`，
  由 API 层翻译为 `502 vendor_unavailable` / `400 vendor_rejected`，
  **不泄露供应商原始报文**。
- **VND-003** 外部调用留痕表 `VendorCall`：kind、provider、operation、
  幂等键、请求摘要（脱敏）、状态、耗时毫秒、外部单号。
  对账与客诉排查的唯一依据。
- **VND-004** 幂等：所有「会花钱/会发送」的操作必须带幂等键，
  相同幂等键重复调用直接返回首次结果，不再打供应商。
- **VND-005** 熔断降级：同一 provider 连续失败超阈值进入冷却期，
  冷却期内直接快速失败（可选降级到 Mock，仅限非资金类）。

## 19.B 支付与提现（P0）

- **VND-010** `PaymentProvider` 接口：
  `create_charge(order_no, amount_cents, subject)` → 支付链接/预支付参数；
  `query_charge(order_no)`；`create_payout(order_no, payee, amount_cents)`；
  `query_payout(order_no)`。
- **VND-011** 充值改为**两阶段**：下单（`PaymentOrder` pending）→ 供应商回调/主动查询
  确认成功 → 才入账钱包。杜绝「未收到钱就加余额」。
- **VND-012** 回调验签：签名不通过一律拒绝；回调**幂等**（同一外部单号只入账一次）；
  回调金额与订单金额不一致则标记 `mismatch` 并告警，不入账。
- **VND-013** 提现打款走 `create_payout`，落地为 `payout_ref`；
  失败/退票回滚为可用余额并记账，保持四不变量。
- **VND-014** `MockPaymentProvider`：即时成功，保留现有测试行为，CI 缺省。

## 19.C 短信与实名（P0）

- **VND-020** `SmsProvider.send_code(phone, code, template)`；
  Mock 固定验证码 `123456`（现状），真实实现走模板短信。
- **VND-021** 验证码服务端生成并**只存哈希**，Mock 环境才回显明文。
- **VND-022** `KycProvider.verify(name, id_no, ...)` → `passed/failed/manual`；
  Mock 直通；真实实现对接三要素/活体。
- **VND-023** 实名原始证件号**不落库明文**：仅存不可逆摘要 + 掩码展示串。

## 19.D 内容安全与存储（P1）

- **VND-030** `ModerationProvider.check(kind, text, media_urls)` →
  `pass/review/reject + labels`；Mock 复用现有本地敏感词机审。
- **VND-031** `StorageProvider`：直传签名 URL、私有读、限时链接；
  Mock 走本地目录。
- **VND-032** 视频转码回调：`content` 模块只认 `StorageProvider` 的回调契约。

## 19.E 配置与安全（P0）

- **VND-040** 所有密钥仅从环境变量读取，**禁止入库、禁止写日志**；
  配置对象暴露 `masked()` 用于健康检查展示。
- **VND-041** `GET /admin/vendors` 展示各 kind 当前 provider、健康状态、
  近 24h 成功率（管理员权限）。
- **VND-042** 启动自检：生产环境（`PLATFORM_ENV=prod`）若任一 P0 kind 仍为 mock，
  启动即失败并打印缺失清单。

## 19.F 验证（P0）

- **VND-050** 支付回调测试：验签失败拒绝、重复回调只入账一次、金额不符不入账。
- **VND-051** 幂等测试：同幂等键重复 `create_payout` 只产生一次外部调用。
- **VND-052** 熔断测试：连续失败后快速失败，冷却结束后恢复。
- **VND-053** 生产自检测试：`PLATFORM_ENV=prod` + mock 支付 → 启动校验报错。

## 验收标准

- 业务模块（wallet/account/content）代码中**不出现任何供应商 SDK 名字**；
- 不配置任何密钥时全部测试通过（Mock 路径）；
- 切换 provider 只改环境变量，无需改代码或迁移数据。
