# 27 · 沙箱桩实现：让预留的接口真的跑得通（STUB）

> ## 检视结论：抽象层建好了，但只发布了退化实现
>
> V43/V49/V50 依次抽出了 `PaymentProvider`、`LedgerBackend`、`SignatureProvider`、
> `NotaryProvider` 等接口，但每个 kind 只发布了**退化实现**：
>
> | 接口 | 已发布实现 | 问题 |
> |---|---|---|
> | `LedgerBackend.custody` | 无可用支付实现 | `MockPaymentProvider` 没有 `split_settle`，切 custody 直接抛错——**整条存管路径零测试覆盖** |
> | `SignatureProvider` | 只有 `platform`（见证签名） | `qualified` 路径只在测试里临时定义一个类，**没有随代码发布** |
> | `NotaryProvider` | 只有 `local`（不背书） | `backed=True` 路径同上 |
> | `PaymentProvider` | `mock`（平台收钱再付钱） | 语义是「钱经过平台」，与合规形态相反 |
>
> **接口预留了却跑不通，等于没预留**：换供应商那天才第一次执行到这些分支，
> 而那正是最不能出错的时刻。
>
> 本 spec 为**每个预留接口补一套形态真实的沙箱桩**，使得：
> 1. 完整业务闭环能在「合规形态」（存管 + 可靠签名 + 第三方存证）下跑通；
> 2. 这些分支**被测试覆盖**，而不是等真接入时才第一次运行；
> 3. 接真实供应商 = 换一个类名，**行为契约已经被测试钉死**。
>
> **红线不变**：沙箱桩同样**不得用于生产**。它们让路径可测，不让平台可上线。

## 27.A 命名与生产拦截（P0）

- **STUB-001** 沙箱实现统一以 `sandbox` 命名（`PLATFORM_<KIND>_PROVIDER=sandbox`），
  与 `mock`/`local` 并列为**非生产实现**。
- **STUB-002** `startup_check` 的判定从「等于 mock 名」改为
  「属于该 kind 的**非生产实现集合**」——否则加了 sandbox 反而绕开了 V49 的红线。
  这是本 spec 最容易做错的地方：**补桩不能削弱拦截**。
- **STUB-003** `/admin/vendors` 与 `/version` 区分三态：
  `production` / `sandbox`（形态真实但仍是桩）/ `mock`（退化实现）。

## 27.B 支付与存管沙箱（P0）

- **STUB-010** `SandboxCustodyPayment` 实现完整的存管形态接口：
  - `create_charge` → 付款进入**存管子账户**（不是平台账户），返回存管流水号；
  - `split_settle(order_no, splits)` → 执行分账指令，返回存管流水号；
  - `create_payout` / `query_payout` → 打款到收款账户；
  - `query_balance(sub_account)` → 子账户余额。
- **STUB-011** 沙箱内维护一份**独立的存管账簿**（与平台钱包分开），
  用于证明「钱不经过平台」这一形态在代码上真的走得通，
  而不是嘴上说说。
- **STUB-012** `CustodyLedger` 接上后，**完整闭环**（充值→托管→放款→分账）
  可在 `LEDGER_BACKEND=custody` 下端到端跑通，每条分账指令带回 `custody_ref`。
- **STUB-013** 沙箱可注入失败：`SANDBOX_FAIL_MODE` 让分账/打款返回失败，
  用于验证**失败路径**（回滚、告警、不半途留脏数据）——
  这类分支比成功路径更需要提前跑过。

## 27.C 签名与存证沙箱（P0）

- **STUB-020** `SandboxCaSignature`：返回签名值 + **证书** + **可信时间戳令牌**，
  `reliability="qualified"`，并实现可验证的 `verify`。
- **STUB-021** `SandboxNotary`：返回 `backed=True` 与存证编号，
  使「第三方背书」路径可测；证据包中的证明力声明随之升级。
- **STUB-022** 两者都必须支持 `verify` 与**篡改检出**——
  桩的价值在于把契约钉死，只返回固定值的桩没有意义。

## 27.D 其余接口补齐（P1）

- **STUB-030** `SandboxKycProvider`：返回 `passed/failed/manual` 三态
  （按测试用证件号触发），使 `manual` 转人工分支可测。
- **STUB-031** `SandboxSmsProvider`：不回显验证码，走**真实通道的严格路径**
  （必须先请求验证码、有效期、尝试次数上限），
  以此覆盖 `mock` 固定码所绕过的那段逻辑。
- **STUB-032** `SandboxModeration`：可配置返回 `pass/review/reject`，
  覆盖转人工分支。
- **STUB-033** `SandboxStorage`：签发直传 URL 形态（`direct_upload=True`），
  覆盖「文件不经过平台」的真实对象存储路径。

## 27.E 一键沙箱自检（P0）

- **STUB-040** `scripts/sandbox_check.py`：把全部沙箱实现装上，
  跑一遍完整闭环并断言：分账带存管流水号、签名为 qualified、
  存证为 backed、证据包证明力声明升级。
  **这就是「接入真实供应商后应当看到的样子」**，可作为对接验收脚本。
- **STUB-041** 该脚本纳入 CI，与既有 mock 冒烟并行——
  两条路径都必须常绿，避免只有一条被维护。

## 27.F 验证（P0）

- **STUB-050** 存管闭环：`LEDGER_BACKEND=custody` + 沙箱支付下跑通主闭环，
  每条分账指令有 `custody_ref`，资金四不变量成立。
- **STUB-051** **补桩不削弱拦截**：`ENV=prod` + 任一 sandbox 实现 → 拒绝启动。
- **STUB-052** 失败注入：分账失败时整体回滚，不留半途状态。
- **STUB-053** 签名升级：沙箱 CA 下 `reliability=qualified`，
  证据包声明变为「构成可靠电子签名」，且**篡改仍被检出**。
- **STUB-054** 存证升级：沙箱存证下 `backed=True`，覆盖区间为全量。
- **STUB-055** 严格短信路径：沙箱短信下**不先请求验证码就注册会失败**，
  覆盖 mock 固定码绕过的逻辑。
- **STUB-056** eKYC 三态：`manual` 返回不置实名、进人工。

## 验收标准

- 完整闭环在**两套配置**下都能跑通并被测试覆盖：
  开发态（mock/internal）与合规态（sandbox/custody）；
- 生产环境对 mock 与 sandbox **一视同仁地拒绝**；
- 接真实供应商只需实现同一组方法，**契约已由测试固定**。
