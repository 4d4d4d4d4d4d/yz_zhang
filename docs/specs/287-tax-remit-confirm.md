
# 287 税款缴库前的人工确认

> 状态：本批实现（V314）。编号 PAY-042d。
> 来源：155 号 spec「没做的」——「税款缴库是调度 job，没有人工四眼；要不要在缴库前加一步人工确认，需与财务流程一起定」；CLAUDE.md「钱、签署、申报、对外发布：AI 只出草稿，人确认」；BACKLOG V314。
> 只增不减：待缴税款在线以下时，缴库 job 照旧一步划出，响应一字不变（`test_tax045_*` 不动）；新增一张表、三个财务接口和后台一块「待确认的缴库」。

## 0. 要解决的问题

缴库 job（TAX-013）每天跑一次，把税款专户的余额整个划出去。划出去的数要和当期申报表上的数一致，可这一步从来没有人看过：代扣算错、退款没冲回、申报口径变了，都要等到对账出差额才发现，那时钱已经划走了。平台其他出钱的路（结算、提现）都有人工确认，唯独缴库没有。

## 1. 业界怎么做

扣缴义务人申报缴税的通常做法：系统按期算出应缴数，由财务与申报表核对后再发起缴款；大额划款要人确认是内控的常规做法（同 148、155 号）。（本批没有另找外部来源。）

## 2. 规则

- 新配置 `PLATFORM_TAX_REMIT_CONFIRM_CENTS`（默认 ¥10 万，与大额结算的超管线同一个数）：待缴余额**达到**它时，job 不动钱，生成一份「缴库草稿」（金额 = 当时的专户余额），通知所有财务角色的管理员一次，响应多 `pending_request_id / pending_cents`，`remitted_cents` 为 0。设成 0 表示每次都要人确认（推荐生产这样配）。
- 已经有一份等确认的草稿时，job 不再生成第二份，也不再通知（返回同一份草稿）。
- **确认**（财务）：只划草稿上那个数（人核对过的数）；草稿之后新代扣的留到下一次。专户余额不够草稿上的数时 409 `tax_remit_insufficient`，写明先查对账、驳回后等下一次重新生成。处理过的草稿再点 409 `tax_remit_already_decided`。
- **驳回**（财务）：必须写明哪里对不上（`reason_required`），不动钱；下一次 job 按当时的余额重新生成草稿。
- 确认与驳回都记审计（`tax_remit_confirm` / `tax_remit_reject`）。
- 只要一位财务确认，不套结算的「第二位财务」与超管分级：缴库的去向是税务机关、金额就是专户余额，没有人能挑金额或收款方；人确认要防的是「数没核对就划走」，一位财务看过就够。这一点写进「没做的」，与财务流程一起再定。

## 3. 数据 / 接口

- 表 `tax_remit_requests`（迁移 `c1d220260071`）：`amount_cents / status（awaiting_confirm、remitted、rejected）/ decided_by / decision_reason / created_at / decided_at`。管理员表，不含用户个人信息，不进注销处置与数据导出。
- `GET /finance/tax-remits?status=`（默认等确认的）、`POST /finance/tax-remits/{id}/confirm`、`POST /finance/tax-remits/{id}/reject`（`{reason}`），都要「财务」角色。
- 共享 SDK：`TaxRemitRequestRow`、`TaxRemitConfirmed`（多 `balance_cents`）；`taxRemits / confirmTaxRemit / rejectTaxRemit`；i18n `tax_remit_already_decided`、`tax_remit_insufficient`。

## 4. 两端

- **Web 后台「平台收支」**：结算待确认下面多一块「待确认的缴库」（没有草稿时不出现）：金额、生成时间、「请与本期申报数核对，确认前钱还在税款专户」；「核对无误，确认缴库」后写出专户余额；「驳回」要填原因，取消就不发。
- **App**：后台只在 Web，不涉及。

## 5. 隐私、授权与边界

只有财务角色能看、能确认或驳回（角色表与对象级授权表都已登记）；草稿行上没有任何用户信息。确认时锁住草稿行，两位财务同时点只有一位成功。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_tax_remit_confirm.py`（4 条：达到线只出草稿、不重复生成、只通知财务、只划草稿上的数并守恒；驳回要理由、不动钱、下次重新生成；余额不足拒绝；线下照旧一步） | 7 处服务端变异全部变红 |
| `web/src/TaxRemitConfirm.test.tsx`（3 条） | 3 处 Web 变异全部变红 |
| 角色表、对象级授权表、功能面清单、i18n、响应形状（`TaxRemitRequestRow`、`TaxRemitConfirmed`） | 登记前分别变红 |
| 迁移 | SQLite 与 Postgres 上 `alembic upgrade head && alembic check` 无漂移 |

变异脚本：`scratchpad/mut314.py`。

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| PAY-042e | 缴库草稿与当期申报表自动比对（要接电子税务局的申报数据） | 台账「外」 |
| PAY-042f | 缴库草稿等确认超过 3 天提醒财务（与申报期限对齐） | 台账「欠」 |
