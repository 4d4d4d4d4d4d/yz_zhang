# 193 App 单测断言失败时报告器崩溃与本地模拟 CI 布局

> 状态：本批实现（V228）。编号 CI-004（并关掉 CI-002）。
> 来源：V220 做变异红验时，App 那一处变异让 jest 挂了十几分钟；单独重跑时整个测试文件报 `TypeError: (0 , _prettyFormat.format) is not a function`，看不到哪条断言没过。台账 CI-002「本地回归模拟 CI 的依赖布局」。
> 只增不减：App 的单测一条不删；兜底能力（共享 SDK 源码在 CI 上能找到 app 的依赖）保留，只换配置项。
> 写明的行为变化：`app/package.json` 的 jest 配置从 `moduleDirectories: ["node_modules", "<rootDir>/node_modules"]` 改为 `modulePaths: ["<rootDir>/node_modules"]`；`tools/regress.sh` 多一步「CI 依赖布局下的 App 单测」。

## 0. 要解决的问题

CI-001（V212 那批）为了让 GitHub CI 的 App job（只装 app 的依赖、没有根 node_modules）能跑通，把 `<rootDir>/node_modules` 写进了 `moduleDirectories`。CI 是绿了，但带来两个问题：

1. **断言一失败 jest 就崩**：`moduleDirectories` 里的绝对路径会在**每一层**目录的查找里都插一次。jest 自己的内部模块（jest-circus 依赖的 pretty-format 29.7）于是先找到 app 顶层那份 24.9（Expo 的依赖带进来的），只要有一条 App 断言失败，jest 格式化错误信息时就抛 `_prettyFormat.format is not a function`：整个文件记 0 条、看不到哪条没过；机器负载高时还会挂住不退出。V213 写 App 探针时已经撞过一次（当时绕开了，没查根因）。
2. **本地回归碰不到 CI 的依赖布局**（CI-002）：本机根目录什么都装着，CI-001 那类「CI 上找不到依赖」本地永远复现不了。

## 1. 业界怎么做

Jest 文档：`moduleDirectories` 是「从当前目录逐层向上查找的目录**名**」（默认 `["node_modules"]`）；`modulePaths` 是「额外的绝对路径，相当于设置 `NODE_PATH`」，在正常查找都找不到之后才用（<https://jestjs.io/docs/configuration#modulepaths-arraystring>、<https://jestjs.io/docs/configuration#moduledirectories-arraystring>）。要的兜底就是后者。

## 2. 数据

无。

## 3. 改动

| 位置 | 改动 |
|---|---|
| `app/package.json` | `moduleDirectories` → `modulePaths: ["<rootDir>/node_modules"]` |
| `tools/regress.sh` | 新一步：把 `app/` 与 `packages/core/` 复制到一个没有根 node_modules 的目录，复制一份 app 的依赖，跑 `gig.test`、`profiles.test`、`screenBoundary` 三个引用共享 SDK 的测试；非 0 退出写「步骤失败」 |

验证（本机）：

- 改后：故意让一条 App 断言失败，jest 正常报出「Unable to find an element…」与 1 failed / 3 passed；
- 模拟 CI 布局：改后 15 条全过；把兜底去掉，原样复现 CI-001 的报错 `Cannot find module '@babel/runtime/helpers/interopRequireDefault' from '../packages/core/src/i18n.ts'`；
- App 全量 431 条全过。

## 4. 两端

不涉及界面。

## 5. 隐私、授权与边界

不涉及。模拟布局每次复制约 450 MB 的 app 依赖，跑完即删。

## 6. 闸门与红验

`server/tests/test_ci_portability.py`：

| 闸门 | 红验 |
|---|---|
| 兜底在 `modulePaths` 里；`moduleDirectories` 不许放绝对路径 | 改回 CI-001 的写法 → 红 |
| `regress.sh` 有「CI 依赖布局下的 App 单测」一步，并算进失败 | 去掉这一步 → 红 |

退役的断言：原 `test_app_jest_falls_back_to_app_node_modules_for_shared_sdk_sources` 断言「`<rootDir>/node_modules` 在 `moduleDirectories` 里」——那正是本批要去掉的写法；同名测试换成上表第一行的两条更严的断言，意图（CI 上找得到依赖）不变。

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| — | 无 | — |
