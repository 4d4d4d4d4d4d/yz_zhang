# 189 App 主框架每一屏的畸形响应探针

> 状态：本批实现（V216）。编号 APP-099。
> 来源：185 号 spec「没做的」——「App 上任务详情以外的二级块逐块探针」；BACKLOG V216。完整运行时校验（APP-098）拆到 V218。
> 只增不减：`DiscoverHost`、`CooperateHost` 原样，只是导出给探针用；页面行为不变。

## 0. 要解决的问题

185 号的 App 探针覆盖了钱包、我的空间、别人的空间、消息和 22 个子页，但主框架的另几屏没探：发现（含空间发现、内容流、视频流、搜索）、合作（任务列表与发布入口）、发布。扩进来后又查出 3 处会整屏落到兜底：

1. **空间发现**：响应是 `null` 时，`setRows` 的更新函数在渲染时才读 `r.items`，`try/catch` 接不住，整屏崩。
2. **发现页**默认就是空间发现，同上。
3. **内容流**：`useReduceMotion` 里 `AccessibilityInfo.isReduceMotionEnabled?.()` 只防住了「没有这个函数」，没防住「函数在但返回 undefined」（老版本 RN、Web 垫片），`.then` 直接抛错。注释写的是「取不到就按 false」，代码没做到。

## 1. 业界怎么做

React 文档提醒：传给 `setState` 的更新函数在渲染阶段执行，必须是纯的、不会抛错（<https://react.dev/reference/react/useState#setstate>）。所以要在调用 `setState` 之前校验响应，而不是在更新函数里读它的字段。

## 2. 数据

无。

## 3. 接口

无新接口。

## 4. 两端

- **App**：空间发现不像样时显示 `MALFORMED_TEXT`；`useReduceMotion` 用 `Promise.resolve` 包一层，取不到按 false（内容流的视差动画照常）。
- **Web**：路由探针已覆盖全部页面（185 号），不涉及。

## 5. 隐私、授权与边界

无变化。

## 6. 闸门与红验

`app/screensResilience.test.tsx` 加 7 屏（发现、合作、发布、内容流、搜索、空间发现、视频流）× 四种畸形响应 = 28 条，共 133 条：

| 闸门 | 红验 |
|---|---|
| 内容流不因取不到「减少动态效果」而崩 | 去掉 `Promise.resolve` → 4 条红 |
| 空间发现不像样只说明原因 | 去掉 `hasLists` → 红 |

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| APP-098 | 对象响应的完整运行时校验（按 types.ts 生成校验器） | BACKLOG V218 |
