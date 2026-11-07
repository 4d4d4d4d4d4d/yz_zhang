# 76 没有人能核过它（TEAM-031 / CERT-030 / UMOD-030 / CS-030 / SECEV-030 / CLI-080 / ADMIN-070）

> 状态：本批实现（V101）
> 依赖：12 号（管理后台）、53 号（团队账户）、51 号（资质核验）、39 号（上传审核）、
> 57 号（客户端可达性闸门）、73 号（运营侧监督）

## 0. 探针

先问一个很小的问题：**一个团队提交了营业执照，谁来核？**

```
POST /teams/2/company            → 200  verify_status = pending
POST /admin/teams                → 404
GET  /admin/teams/pending        → 404
POST /admin/teams/2/verify       → 404
POST /teams/2/verify             → 404
团队核验状态: pending | 开票拦截: 团队企业信息尚未通过核验，暂不能开具发票
```

**这个端点不存在。** 全仓唯一把 `verify_status` 写成 `"verified"` 的地方是
一条测试——它直接写库：

```python
with SessionLocal() as db:
    t = db.get(Team, team_id)
    t.verify_status = "verified"        # tests/test_team_accounts.py
    db.commit()
    assert team_service.can_invoice(db.get(Team, team_id)) == ""
```

于是 `can_invoice()` 在生产里**永远返回那句拦截语**：没有任何团队能开票，
也没有任何人能核过任何一个团队。而测试是绿的——**因为测试自己把状态改了，
所以没有人发现没有人能改它**。

第二个探针，把范围拉开：

```
服务端 /admin 端点共 40 条
管理后台实际调用的 SDK 方法 15 个
```

## 1. 为什么会漏成这样

V82 立了覆盖闸门（服务端新增用户可达端点，必须给出「端上怎么到达」或
「为什么不给端」），而它的扫描器第一行就把整个运营面排除了：

```python
if "/admin" in rel or "/jobs" in rel:
    continue          # 运营后台与调度端点不面向普通客户端
```

这句注释是对的——**运营端点确实不面向普通客户端**——但它回答的是
「要不要放进用户 SDK」，被当成了「要不要有人接」。于是四十条运营端点
整体退出了任何覆盖检查，V96、V98 各自靠**人工清点**捞回来几条
（提现复核、审计日志、封禁影响面、平台财务、公告、可疑活动）。
人工清点能捞到看得见的，捞不到「端点压根不存在」这一类。

V98 建的 `ADMIN_CONSOLE` 表是一张**手挑的必达清单**，不是覆盖闸门：
它只回答「表里这几条做到了没有」，不回答「有没有第四十一条没人管」。

## 2. 判定标准（沿用 V98，写清楚以便照着分类）

> **只有运营/风控能做，而不做就有人的钱或权利卡住。**

按这条过一遍四十条：

| 不做会怎样 | 端点 | 结论 |
|---|---|---|
| 团队永远不能开票，也没人能核 | （**端点不存在**） | 本批补 |
| 受限类目的资质申请永远没人看，用户接不了单 | `certifications/pending` `decide` `revoke` | 本批接 |
| 机审拿不准的图片永远挂在站上/卡着 | `uploads/pending` `uploads/{name}/resolve` | 本批接 |
| 用户的工单没人回，SLA 是摆设 | `tickets` `tickets/{id}/resolve` | 本批接 |
| 被误封的公司出口 IP 打不开门 | `security` `security/unban` | 本批接 |
| 线下任务发不出去（未开通城市） | `cities` `cities/{id}` `categories` `categories/{id}` | 本批接 |
| 没有补贴活动就是没有补贴，不卡任何人 | `coupons` `campaigns` `subsidy-pool/fund` | 豁免 |
| 没有 AI 执行者只是少一种执行者 | `agents` 三条 | 豁免 |
| 不做只是看不到数，不卡人 | `metrics` `funnels` `market-health` `north-star` `aml/stats` `settlements/verify` `vendors` `audit-log`(已接) | 豁免/已接 |
| 调度器在跑 | `jobs/reconcile` | 豁免 |

「豁免」不等于「不该做」，只等于**不属于这条判定标准**；它们仍然在
72 号台账里挂着。

## 3. TEAM-031 团队企业信息核验

新增两条端点：

- `GET /admin/teams/pending`：待核验的团队，带**执照影像的鉴权 URL**
  （沿用 CERT-010：证件影像走 `/files/{name}/secure`，不是匿名能力 URL）。
- `POST /admin/teams/{team_id}/verify`：`{approve, reason}`。

三条硬要求：

1. **驳回必须写理由，并且送到 owner 面前**。这是 V92 那条的又一次：
   「必须写」和「送到了」是两件事。owner 收不到理由就不知道要补什么材料，
   只能反复提交同一份。
2. 核验结果落审计（`team_verify`）——它决定这个团队能不能开票，是有后果的动作。
3. 通过后 `can_invoice()` 必须真的放行；这条由**闭环测试**钉住，
   而不是靠一条直接写库的断言。

## 4. CLI-080 把运营面纳入覆盖闸门

新闸门的形状与 V82 的 CLI-060 相同，作用域是 `/admin`：

> 服务端每一条 `/admin` 端点，**要么**管理后台里真的有代码调它，
> **要么**在豁免表里写一句人话理由。

细节（都是前面几批踩过的坑）：

- 判「真的调它」沿用 `tests/clientscan.py` 的单一实现，且要求
  **组件挂载**（V96 的教训：组件函数留在文件里、没挂上，扫描器照样绿）。
- 豁免理由**不许包含「还没做 / 待补 / TODO」这类措辞**：那不是理由，
  是欠账；欠账归 72 号台账管，不该伪装成豁免。
- 豁免表与服务端双向对齐：豁免了一条已经不存在的路径也红
  （否则删了端点、豁免留着，闸门就慢慢空掉）。
- 扫描器自己先会红：扫不到路径、或扫不到已知调用，测试自己失败。

## 5. ADMIN-070 审计行的 target 必须是整数

顺手掉出来的一条类型漂移：

```python
record_audit(db, admin.id, "certification_decide", "certification",
             str(application_id), ...)     # target_id: int | None
record_audit(db, admin.id, "agent_create", "agent", str(agent_user.id), ...)
```

`AdminAudit.target_id` 是 `Integer`。SQLite 会**默默接受**字符串并存进去，
所以本地全绿；Postgres（41 号 spec 的生产路径）会直接拒绝这条 INSERT——
而它在一个 `try` 之外的写入点上，**处置动作会连带失败**。

修两处，并加一条 AST 闸门：`record_audit` 的第五个实参不许是 `str(...)` 调用。
用 AST 而不是正则，理由与 V58 那条状态机闸门相同：正则读不懂调用结构。

## 6. 验收点

| 编号 | 验收点 |
|---|---|
| TEAM-031 | 提交企业信息后，管理员能在待核验列表里看到它（含执照鉴权 URL） |
| TEAM-031 | 核验通过后 `can_invoice()` 放行——走 HTTP，不直接写库 |
| TEAM-031 | 驳回必须写理由，且理由送到 owner 的通知里 |
| TEAM-031 | 核验留审计 |
| CERT-030 | 资质申请能在后台看到、能通过/驳回，用户随后真的能接受限类目的单 |
| UMOD-030 | 机审拿不准的图片能在后台处置，被拒时上传者收到通知 |
| CS-030 | 工单能在后台回复，回复送到提单人 |
| SECEV-030 | 被封的 IP 能在后台解封 |
| CLI-080 | 每条 `/admin` 端点要么后台真的调用，要么豁免表里有人话理由 |
| CLI-080 | 豁免理由里出现「还没做」一类措辞即红 |
| CLI-080 | 豁免了不存在的路径即红；扫描器扫不到时自己先红 |
| ADMIN-070 | `record_audit` 的 target_id 不许传字符串（AST 闸门） |

## 7. 这一批没做的

- **城市与类目的界面只做开通/停用与新增**，没有做排序、图标、多语言名称。
- 资质核验**没有做证件 OCR 与发证机关联网核验**（51 号的外部依赖照旧）。
- 工单没有做**分配与转交**（谁负责哪一单），也没有 SLA 超时催办——
  催办的机制 V100 已经建好，接上是下一批的事。
- 上传审核队列**没有分页**（与 PAY-043 同一类）。
- **CLI-081**：`/jobs` 端点仍整体在覆盖闸门之外。它们由 32 号的调度表
  双向闸门覆盖，不是无人看管，但两套闸门各管一半这件事值得记着。
- 豁免表里的「不卡人」判断是**我写的**，没有运营确认过。真实运营
  可能认为漏斗与市场健康度是每天要看的东西。
