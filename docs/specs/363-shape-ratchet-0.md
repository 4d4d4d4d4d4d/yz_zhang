
# 363 形状闸门认 null / 联合 / Partial，未验证调用点清零

> 状态：本批实现（V390）。编号 CLI-083b。
> 来源：361 号 spec 第 7 节「没做的」；BACKLOG V390。
> 只增不减：SDK 只加字段（`PublicProfileExtras`），不删方法；服务端不改。
> 写明的行为变化：V388 的闸门自测原来断言「`Partial<Me> & {…}` 读不出」，本批让比较器认得 `Partial<X>`，那一条改成断言新行为（字段全部可选），另加一个仍然读不出的例子（`Omit<…>`）。

## 0. 要解决的问题

剩下 13 个未验证调用点，多数是比较器认不出的声明写法：

- `MachineMandateView | null`（没授权过的 Key 返回 null）；
- `{ … } | PlatformSettlePending`（平台结算直接成功，或进四眼等第二人）；
- `Partial<Me>`（别人的名片页）。

另有几个是要造复杂数据的接口：智能体执行、核验单（列表、详情、结论）、争议申诉、待审团队、经验校准与撤回。

## 1. 做法

- `_shape_variants(decl)`：一个声明可能的几种对象形状。去掉 `null` / `undefined`；`A | B` 每个对象都是候选；`Partial<X>` 即 X 的字段全部可选。
- `_assert_inline_shape`：值是 null 且声明允许 null 就通过；否则符合任何一个候选就算对；都不符合时报每个候选的第一条问题。原有的三条报错文字（「声明了服务端没给的字段」「没声明的字段」「类型对不上」）不变，原有自测照过。
- `_object_fields` 认 `Partial<X>`，交叉类型里出现也认。
- 扫除闸门把 `X | null` 归一成 `X` 再去找已有断言。
- 第五批真实响应断言：
  - 智能体执行（`runAgent`）、核验单列表、详情与结论（`openVerificationOrders`、`verificationOrder`、`submitVerificationOutcome`）；
  - 争议申诉（`appealDispute`）、名片页（`publicProfile`）、平台结算（`settlePlatform`）；
  - 待审团队（`pendingTeams`）、未授权的 Key（`machineMandate` 的 null）；
  - 经验校准样本与撤回（`knowledgeCalibrationPairs`、`retractKnowledgeTask`）。
- 两个写进豁免表，都写明理由：
  - `searchSuggest`：返回 `string[]`，没有字段可比；
  - `signVideoUpload`：本地存储按设计拒绝直传，真实签名响应要接对象存储（「外」）。

## 2. 扫出来的问题

| 接口 | 问题 | 改法 |
|---|---|---|
| `publicProfile` | 服务端一直返回服务定价、可接单时间、是否在接单（ACC-013 名片页承接下单），SDK 只声明了 `Partial<Me>`，客户端看不见这三项 | 新接口 `PublicProfileExtras`，声明改成 `Partial<Me> & PublicProfileExtras` |

## 3. 结果

- 未验证调用点：13 → **0**；棘轮 `MAX_UNVERIFIED` 13 → 0。从此新加一个 SDK 调用点，既没有静态比对、也没有真实响应断言时，扫除闸门直接红。
- 这一路（V384 → V390）从 78 降到 0，改对的 SDK 声明共 16 处。

## 4. 两端

不涉及界面改动（SDK 类型改动两端类型检查照过）。

## 5. 隐私、授权与边界

不涉及。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `test_client_shape_alignment.py`（交叉类型与 Partial 自测）、`test_response_shape_sweep.py`（棘轮 0、豁免表）、`test_shape_sweep_v384.py`（22 条） | `scratchpad/mut390.py` 共 8 处，全红：<br>null 放行去掉；`Partial` 不认（真实断言红、自测红）；联合改成「每个候选都要符合」；`PublicProfileExtras` 去掉一个字段；豁免表的方法名写错（棘轮红）；`X \| null` 不归一，同时去掉 `machineMandate` 的方法名断言（棘轮红）。<br>首轮 2 处存活，都已处理：<br>① 测试里调了一个不存在的「撤销授权」接口，拿到的并不是 null。改成用一把从没授权过的 Key，并断言返回值确实是 null。<br>② `X \| null` 的归一与方法名断言是两条互为备份的路，单独去掉任何一条都还被另一条覆盖。改成两条同时去掉验证 |

## 7. 没做的

无新增欠账（CLI-083b 清零）。
