
# 312 响应形状棘轮收紧并再验一批调用点

> 状态：本批实现（V339）。编号 CLI-083b（部分）。
> 来源：72 号台账 CLI-083b「响应形状仍有 103 个调用点未验证」；BACKLOG V339。
> 只增不减：服务端响应一个字段都没改；SDK 两处声明**改对**（只加字段、旧名留作可选），其余只加测试与收紧一个数。

## 0. 要解决的问题

响应形状闸门（V125）对「handler 返回变量 / 列表推导、静态读不出键」的调用点只能记账，用棘轮钉住数目只许降。这个数已经降到 95，棘轮还停在 103——**留着 8 个空位，等于允许悄悄回涨 8 个**。V334 把 `updateCategory` 的返回改成变量时就悄悄占了一个空位，没有任何东西红。

## 1. 业界怎么做

契约测试（consumer-driven contract）以真实响应对照客户端声明；静态推断不了的部分用「只许降」的计数器管住存量。（本批没有另找外部来源。）

## 2. 做了什么

- 新增 `server/tests/test_shape_sweep_more.py`（3 条），用真实响应对照 SDK 声明：`listApplications`、`Recommendation`、`taskTemplate`、`cancelTask`、`myBlocks`、`ContentItem`（`myDrafts` 等）、`categoryDemand`、`trendingTerms`、`updateCategory`（单张与多张资质两种响应）。列表类的先断言非空——静态扫描只认「写了断言」，不认「断言跑没跑」。
- **两处真问题**（验的时候才发现）：
  - `myDrafts` 声明成 `{id, title, created_at}`，服务端给的是完整的内容行：改成 `ContentItem[]`（超集，调用方不受影响）。
  - `categoryDemand` 声明的是 `open_tasks` / `suppliers`，服务端从来给的是 `open_demand` / `supply`（还有供需比 `demand_supply_ratio`）：改成真实字段；旧名留作可选、恒为空并注明别用（目前两端都还没调用它，所以没有界面受影响）。
- 棘轮 `MAX_UNVERIFIED` 103 → **78**。

## 3. 数据 / 接口

不涉及。

## 4. 两端

不涉及界面。

## 5. 隐私、授权与边界

不涉及。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `test_response_shape_sweep.py` 的棘轮（78） | 改成 77 → 红 |
| `server/tests/test_shape_sweep_more.py`（3 条） | 服务端去掉供需比 → 红；报名行去掉 status → 红；SDK 改回旧名 → 红 |

变异脚本：`scratchpad/mut339.py`（4 处全红）。

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| CLI-083b | 还有 78 个调用点未验证（逐批补真实响应断言，或让 dump 函数本身被静态读到） | 台账「欠」（数字更新） |
