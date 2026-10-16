# 175 替别人发单：发单人与服务对象分开

> 状态：本批实现（V202）。编号 SCN-119。
> 来源：173 号 spec 第 7 节「没做的」——「替别人发单：子女替爸妈发、主人替家里发，发单人与服务对象是两个人；现在只能把爸妈的地址写进说明里，接单前就被看到」；BACKLOG V202；VISION 1.7「在外地的子女」。
> 只增不减：不勾「替别人发」时发单与原来完全一样；`address_exact` 的可见性（GEO-004）不变；定期清理（GEO-024）原有的坐标清理不变，响应多一个键。
> 写明的行为变化：没勾「替别人发」却带了服务对象的称呼、联系方式或「问过本人」，服务端拒绝（`recipient_without_on_behalf`），免得悄悄带上别人的信息。

## 0. 要解决的问题

- 「给爸妈办事」包（173 号）上线后最直接的缺口：子女替爸妈发单，平台只认识发单人。爸妈的称呼、到场联系谁只能写进说明——说明是公开的，接单前所有人都看得到。
- 没有任何地方提醒「先问过本人」，也没有记录；第三人的电话结束后永远留在库里，注销也不清。

## 1. 业界怎么做

| 做法 | 说明 |
|---|---|
| 替别人叫车（Uber「Request a ride for someone else」） | 下单人付款；乘车人的姓名给司机，行程信息用短信发给乘车人；号码是否直接给司机各报道说法不一（<https://techcrunch.com/2017/06/27/uber-now-lets-you-request-a-ride-for-somenoe-else>、<https://www.phonearena.com/news/Uber-adds-ability-to-book-rides-for-others-who-lack-smartphones_id95412>） |
| 个人信息保护法 | 处理个人信息应取得个人同意（第十三条），并限于实现目的的最小范围（第六条） |

本批取：下单人付款、托管、验收（钱的关口不变）；服务对象的**称呼**与**到场联系**单独填、只给成交双方；发之前确认问过本人并记下时间；结束 30 天后清掉联系方式。

## 2. 数据

`tasks.on_behalf`（布尔）、`recipient_label`（≤20）、`onsite_contact`（≤40）、`recipient_consent_at`（确认问过本人的时间）。迁移 `c1d220260040`（SQLite 与 Postgres 都 `upgrade head && check` 过）。

## 3. 接口

| 接口 | 变化 |
|---|---|
| `POST /tasks` | 多 `on_behalf`、`recipient_label`、`onsite_contact`、`recipient_consented`。勾了：称呼必填（`recipient_label_required`）、必须确认问过本人（`recipient_consent_required`），记下确认时间；没勾却带了：拒（`recipient_without_on_behalf`） |
| 返回 `Task` 的接口 | 多 `on_behalf`（人人可见）、`recipient_label` 与 `onsite_contact`（**只给成交双方**，别人是空串；与 `address_exact` 同一条判断） |
| 多人、多天的名额 | 每个名额带着同样的服务对象（每个帮手都要知道找谁） |
| 周期单的下一期 | 照样替同一个人 |
| `POST /tasks/jobs/purge-locations` | 结束满 30 天的任务清掉 `onsite_contact`（称呼留着，账单与纠纷要认得是哪一单），响应多 `purged_contacts` |
| `POST /open/v1/tasks`（机器授权） | `on_behalf` 一律拒（`on_behalf_needs_human`）：问没问过本人只能由人确认 |
| 开放平台出站（webhook） | `onsite_contact`、`recipient_label` 进敏感键黑名单，永不出站 |
| `GET /users/me/export` | 发单人自己的替别人发的单带上称呼、联系方式、确认时间；接单人的导出不带 |
| 注销 | 发单人注销时，他替别人发的单的称呼改成「（已注销）」、联系方式清空；「替别人发」这个事实留着 |

## 4. 两端

- **Web 发布页**：勾「替别人发（家人、朋友）」后出现：服务对象称呼、到场联系、「已经问过本人」，并提示身份证号、银行卡、验证码不要写。不勾不带。
- **App 发布页**：同样三项（勾选框是无障碍 checkbox）。
- **两端详情页**：替别人发的单写明「替别人发的单」；成交双方多看到「服务对象「我妈」· 到场联系 …」，别人看到「服务对象与到场联系方式成交后可见」。

## 5. 隐私、授权与边界

- 服务对象的信息是**第三人的个人信息**：只在成交后给接单人；不进开放平台出站；结束 30 天后清联系方式；发单人注销时清空。
- 「问过本人」只能由人勾选（机器授权拒），平台记下确认时间作为发单人已告知的凭据；平台不替发单人核实。
- 钱、发布、验收都还是发单人本人（不变）。

## 6. 闸门与红验

20 处变异全部变红（`scratchpad/mut202.py`；最初 1 处存活——接单人导出带上了第三人信息，补了用例后变红）：

| 闸门 | 测试 | 红验 |
|---|---|---|
| 称呼与到场联系只给成交双方；广场列表也不带 | `server/tests/test_on_behalf.py::test_recipient_details_are_only_for_the_two_parties` | 去掉 `is_party` 判断（两处）→ 红；`on_behalf` 恒为 false → 红；不记确认时间 → 红 |
| 称呼必填、必须问过本人、没勾不收 | `test_must_name_the_recipient_and_confirm_consent` | 三条规则分别去掉 → 红 |
| 名额带着服务对象 | `test_slots_carry_the_recipient…` | 名额不复制联系方式 → 红 |
| 结束 30 天后清联系方式、称呼留着 | `test_contact_is_purged_30_days_after_close…` | 只数不清 → 红 |
| 导出给发单人、注销清空 | `test_export_carries_it_for_the_poster_only_and_deletion_erases_it` | 注销不清联系方式 → 红；导出不带确认时间 → 红 |
| 接单人的导出不带第三人信息 | `test_executor_export_does_not_carry_the_third_party` | 接单人也带 → 红 |
| 机器不能代勾、出站不带 | `test_machine_api_cannot_tick…`、`test_openapi_webhooks_never_carry…` | 去掉黑名单 → 红；去掉机器拒绝 → 红 |
| Web 发布与详情 | `web/src/OnBehalf.test.tsx` | 不勾也带 → 红；「问过本人」写死 false → 红；不显示到场联系 → 红 |
| App 发布与详情 | `app/onBehalf.test.tsx` | 同上三处 → 红 |

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| SCN-122 | 服务对象自己也能看到进度（给爸妈发一条只读链接或短信：谁来、几点到） | 欠：要短信通道（「外」）或免登录只读链接的安全设计 |
| SCN-123 | 发单后改服务对象（换人、改联系方式）：现在要取消重发 | 欠 |
| — | 平台核实「问过本人」 | 意：平台只记录发单人的确认，不替人核实，也不应联系第三人 |
