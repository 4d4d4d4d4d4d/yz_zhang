
# 361 形状比较器认交叉类型、棘轮 22 → 13

> 状态：本批实现（V388）。编号 CLI-083b。
> 来源：359 号 spec 第 7 节「没做的」；BACKLOG V388。
> 只增不减：SDK 只把错误或过窄的声明改对（见第 2 节），不删方法；服务端不改。

## 0. 要解决的问题

剩下 22 个未验证调用点里，一半的 SDK 声明是交叉类型（`Task & { slots?: Task[] }`、`Mission & { steps; timeline }`、`Contract & { coupon_discount_cents? }`）。比较器只认内联字面量和具名接口，交叉类型整体读不出，于是这些接口既没有静态比、也没法写真实响应断言。

## 1. 做法

- `_inline_fields` 认交叉类型：顶层按 `&` 切开，每一部分按「内联字面量或具名接口」取字段再合并；任何一部分认不出（`Partial<…>`、未知名字）就整体放弃，不猜。数组外壳（`Array<A & {…}>`）照旧剥掉。
- 这一改同时作用于静态比对（扫除闸门）与 `_assert_inline_shape`；静态比对的 238 个调用点照样 0 处不一致。
- 闸门自测 `test_cli083b_intersection_types_merge_their_parts`。
- 第四批真实响应断言：发单（`createTask`）、托管（`fundContract`）、任务编排（`getMission`、`tickMission`、`cancelMission`）、争议和解（`proposeSettlement`、`acceptSettlement`）、作品评论、拆解模板。

## 2. 扫出来的问题

| 接口 | 问题 | 改法 |
|---|---|---|
| `decompositionTemplate` | 声明 `{ found; items }`，服务端从来不给 `found`，实际是 `{ category, items, source }`——按声明判断「找没找到」永远是假 | 改成实际的三项，`source` 列出四种取值（没有模板时为 `none`） |
| `proposeSettlement`、`acceptSettlement` | 声明只有 `{ id }` / `{ id, status }`，服务端返回整条争议记录（含刚提出的和解方案、状态） | 改成 `Dispute`（原声明是它的子集，Web 与 App 的调用处类型检查照过） |

## 3. 结果

- 未验证调用点：22 → **13**；棘轮 `MAX_UNVERIFIED` 22 → 13。
- 剩下 13 个：`Partial<Me>`、`string[]`、`X | null`、联合类型（`settlePlatform`）这类闸门比不了的写法，以及要造复杂数据的接口（核验单三个、智能体执行、经验校准与撤回、待审团队、视频直传签名、争议申诉）。

## 4. 两端

不涉及界面改动（SDK 类型改动两端类型检查照过）。

## 5. 隐私、授权与边界

不涉及。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `test_client_shape_alignment.py`（交叉类型自测）、`test_response_shape_sweep.py`（棘轮 13）、`test_shape_sweep_v384.py`（18 条） | `scratchpad/mut388.py` 7 处：不切 `&`（自测红、真实断言红）、认不出的部分跳过而不是放弃（自测红）；`proposeSettlement`、`acceptSettlement` 改回窄声明（棘轮红）；`decompositionTemplate` 加回 `found`（真实断言红）；棘轮改成 12（红）。<br>首轮 1 处存活：`acceptSettlement` 的变异跑错了测试（`_assert_shape(…, "Dispute")` 不读方法声明），改跑棘轮后变红 |

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| CLI-083b | 还有 13 个调用点未验证 | 欠：`Partial<…>` / `X \| null` / 联合类型要比较器再认几种写法；核验单与智能体执行要造数据 |
