# 47 共享类型与文案的漂移，和一个从没装上过的 App（SYNC / APPB）

> 起因：V71 给 `app/` 加了「新依赖必须声明」的闸门（VID-041）之后，
> 我去看这条闸门到底挡住了多大一块地方——结果发现它挡住的那一块，
> 底下整个是空的：**`app/` 目录从来没有被安装过一次。**
> 顺着这条线往回拉，拉出了一条更贵的：共享 SDK 的类型漂了，
> 于是**执行方被冻结的保证金，在两个端上都没有一处说得清楚**。

## 0. 三个已复现的事实

这一批不是从「该做什么功能」开始的，是从三次实测开始的。

### 事实一：`cd app && npm install` 直接失败

`app/README.md` 里白纸黑字写着运行方式：

```bash
cd app && npm install && npx expo start
```

实测第一步就炸：

```
npm error code E404
npm error 404 Not Found - GET https://registry.npmjs.org/@platform%2fcore
npm error 404  '@platform/core@*' is not in this registry.
```

原因：`app/package.json` 写的是 `"@platform/core": "*"`，而根 `package.json`
的 `workspaces` 只有 `["packages/*", "web"]`——**`app` 不是工作区成员**，
根安装不会给它建链接；它自己安装时 `*` 被当作「去 registry 找一个叫
`@platform/core` 的公开包」，那个包不存在。

也就是说：README 里这条命令，从写下来的那天起就没有成功过一次。

### 事实二：一旦真的 typecheck，立刻查出一处类型错误

把 `app/` 装起来、配上 `tsconfig.json` 之后第一次跑 `tsc --noEmit`：

```
App.tsx(210,25): error TS2339: Property 'deposit_cents' does not exist on type 'Contract'.
App.tsx(210,72): error TS2339: Property 'deposit_cents' does not exist on type 'Contract'.
```

查下去发现**服务端是对的、App 是对的、类型是错的**：

- `server/app/modules/contract/router.py:53-54` 确实返回了
  `deposit_cents` 与 `deposit_status`；
- `app/App.tsx:210` 确实读它，运行时能拿到值；
- 只有 `packages/core/src/types.ts` 的 `interface Contract` 里没有这两个字段。

这条本身不致命（运行时是对的），致命的是它的**下游**——见事实三。

### 事实三：保证金被冻结，但没有任何一个界面说它是什么

`Contract` 类型里没有 `deposit_cents`，于是 Web 端压根没写这块显示。
把整条链路跑一遍看用户看到什么：

| 环节 | 实际发生 | 用户看到 |
|---|---|---|
| 发布方发单时填「保证金 ¥50」 | `Publish.tsx` 正常提交 | 正常 |
| 执行方接单 | `wallet.freeze_deposit()`：可用 −5000，冻结 +5000 | **可用余额少了 ¥50** |
| 执行方看合约页 | Web 的 `TaskDetail.tsx` 不显示保证金 | 合约上**没有一个字**提到保证金 |
| 执行方看钱包 | 「冻结中 ¥50.00」 | 一个数字，**不说是被什么冻的** |
| 执行方看账单流水 | 流水里有这一笔 | 类型一列写着 **`deposit_hold`** |

最后一格是实测打出来的：

```
worker ledger kinds: ['deposit_hold', 'topup']
UNLABELED ROWS SHOWN TO USER: [('deposit_hold', -5000)]
```

**一个中文界面里，用户的 ¥50 不见了，唯一的解释是一行英文标识符。**

## 1. 为什么会漂到这个程度：两份手抄的清单

两条根因是同一件事的两面——**跨边界的约定被手抄了一份，然后没人对过**。

### 1.1 账本科目的中文名是手抄的

`web/src/pages/Wallet.tsx` 里有一张 `KIND_LABEL` 表，8 条。
服务端能产生多少种科目？用 AST 扫 `_log()` 调用数出来是 **20 种**：

- 字面量 16 种：`topup` `withdraw` `withdraw_hold` `withdraw_refund`
  `escrow_hold` `escrow_release` `refund` `fee` `platform_topup`
  `platform_settle` `deposit_hold` `deposit_return` `deposit_forfeit`
  `dispute_split` `tax_withheld` `tax_remit`
- `transfer()` 动态拼出的 4 种：`adjust_in` `adjust_out`
  `subsidy_in` `subsidy_out`

**12 种科目没有中文名**，其中至少 5 种（保证金三态、提现冻结与退回）
是普通用户的日常路径。

而这行代码保证了它永远不会被发现：

```tsx
<td>{KIND_LABEL[e.kind] ?? e.kind}</td>
```

`?? e.kind` 是个合理的兜底——但它**不出错**。服务端加一个科目，
网页不会红、不会报、不会崩，只是默默给用户看英文。
这是这个项目里反复出现的同一类问题：**错了也不会出错的声明**。

### 1.2 共享类型是手写的，而它同时是三方的约定

`packages/core/src/types.ts` 是 Web 与 App 共用的唯一 SDK。它描述的是
**服务端实际返回什么**。但它是人手写的，而服务端的序列化函数改了没人回来改它。
`deposit_cents` 只是被 `tsc` 逮到的那一个——因为 App 恰好读了它。
**没有任何客户端去读的漏字段，永远不会有人发现**：它表现为「这个功能好像没做」。

## 2. 判断：不是补文案，是让它下次漂的时候会红

补 12 条中文、加两个字段，是十分钟的事。但十分钟之后它会重新开始漂，
因为让它漂的那个机制一点没变。所以这一批的重点在闸门上。

### SYNC-001 文案收到 `packages/core`，两端共用一份

标签表从 `web/src/pages/Wallet.tsx` 搬到 `packages/core/src/ledger.ts`，
Web 与 App 都从 SDK 导入。

理由不是「复用」，是**让「唯一一份」这件事在物理上成立**：
放在 Web 里，App 要显示流水就只能再抄一份，于是从两份变三份。

### SYNC-002 科目全集在服务端显式声明，`_log()` 拒绝未声明的科目

第一版我打算用 AST 扫 `_log()` 调用凑出科目全集。写到一半发现它凑不全：
`transfer()` 是 `_log(db, id, f"{kind}_out", …)`，**科目是拼出来的**，
静态扫描只能看到后缀 `_out`，前面那半截要靠猜调用方传了什么。
「靠猜」的闸门不是闸门。

改成让服务端**自己说清楚**：`wallet/service.py` 里声明

```python
LEDGER_KINDS: frozenset[str] = frozenset({... 20 条 ...})
```

并且在 `_log()` 里加一条硬检查——`kind` 不在全集里就 `ValueError`。

这条检查会在资金路径上抛异常，是有意的：未声明的科目意味着有人新加了
一种流水却没给它名字，**那一笔写进账本之后就永远是一行英文**。
在写入点炸掉，比写进去之后靠肉眼发现便宜得多；而且下面的 CI 闸门
会让它根本走不到生产。`transfer(kind=...)` 的入参同样受这条约束。

于是比对变成两个 Python/TS 对象之间的事，不再有推断：

`LEDGER_KINDS` ↔ `packages/core/src/ledger.ts` 的键集合，**两个方向都查**：

- SDK 缺 → 用户看英文（现在这个洞）；
- SDK 多 → 服务端删过科目而文案没跟着删，是另一种漂。

### SYNC-003 AST 扫描降级为「第二道」，且扫描器自己不许静默失败

全集声明解决了「有没有名字」，但没解决「声明会不会忘了更新」。
所以 AST 扫描保留，改成查一件更窄、它扫得准的事：
**`_log()` 里出现的每个字面量科目，都必须在 `LEDGER_KINDS` 里**。

写这条扫描时我先写错了一次：`_log(db, user_id, kind, …)` 我按 `args[1]`
取，扫出来是**零个科目**——而「零个科目」会让比对**全绿通过**。

一个会静默返回空集的扫描器，比没有扫描器更坏：它给出一个「已检查」的假象。
所以测试里硬编一条下界断言：扫到的字面量科目数 `>= 14`，且
`deposit_hold` / `escrow_hold` / `tax_withheld` 必须在结果里。
签名一改、扫描一瞎，**先炸的是扫描器自己**。

### SYNC-004 SDK 的 `Contract` 类型要跟服务端的真实响应对齐——也用测试强制

不是靠眼睛比。测试里真的走一遍下单流程拿到 `GET /contracts/{id}` 的 JSON，
取它的键集合，再从 `packages/core/src/types.ts` 里解析 `interface Contract`
的字段名，断言**服务端返回的每个键都在类型里有声明**。

这里用正则解析 TypeScript——DSPC-041 明确说过**不要造通用 TS 解析器**。
这条不违背它：解析范围是**一个已知名字的接口块、每行一个字段**，
属于「枚举 + 逐处精确正则」那一类，不是通用解析。
同样按 SYNC-003 的规矩上下界自检：解析出的字段数 `<10` 直接判失败，
免得正则失配时静默返回空集然后全绿。

反方向（类型里有、服务端没返回）只告警不失败：`milestones?` 这类
可选字段在没有里程碑的合约上本来就不出现，强制双向会逼出假阳性。

这条比 SYNC-002 更值钱：它查的不是文案，是**前后端之间那份没人签字的约定**。

### SYNC-005 补上保证金的显示（这才是用户拿到的东西）

- `Contract` 加 `deposit_cents: number` 与 `deposit_status: string`；
- Web `TaskDetail.tsx` 的合约卡片显示保证金与状态
  （`held` 冻结中 / `returned` 已退还 / `forfeited` 已罚没 / `none` 不显示）；
- 12 条缺失文案补齐。

关于兜底：`?? e.kind` **保留**。理由是显示层的失败方式要选对——
一笔认不出的流水应当显示原始标识符，而不是让整个钱包页空白或报错；
用户至少还能把这串字符发给客服。**防漂的责任在 CI，不在渲染时。**

## 3. APPB：把 `app/` 变成一个真的能装的工程

事实一之后，`app/` 缺的不止一个依赖声明。对着一个空目录逐项补：

### APPB-001 `@platform/core` 用 `file:` 协议

```json
"@platform/core": "file:../packages/core"
```

实测 `cd app && npm install` 成功，1139 个包、29 秒。

**为什么不把 `app` 加进根 workspaces**：那样根目录的 `npm install`
（以及 CI 里 web 的 `npm ci`）会连 react-native 与 expo 一起装进来，
Web 的流水线要为一个它不碰的端付出好几百 MB 与几分钟。
`file:` 让 `app` 保持独立安装，恰好也是 README 里写的那条命令。

### APPB-002 `babel.config.js`

Expo 的 Metro 靠 `babel-preset-expo` 转 JSX/TS，没有 `babel.config.js`
就没有这个 preset。这不是可选配置，是**没有它 `expo start` 起不来**。

### APPB-003 `metro.config.js`

`@platform/core` 是**符号链接到仓库外的 TypeScript 源码**，不是编译好的包。
Metro 默认只看项目根以下，必须显式：

- `watchFolders` 加上 `packages/core`，否则解析不到；
- `nodeModulesPaths` 同时看 `app/node_modules` 与根 `node_modules`，
  否则 core 的依赖找不着。

**这条是本批唯一没被机器验证的改动**：验证它要真的起 Metro，
而 Metro 要连设备或模拟器，本环境做不到。写法照 Expo 的 monorepo 文档，
但它「对不对」目前只有我的判断背书——记在 APPB-051 里，不当作已验证。

### APPB-004 删掉 `expo-image-picker` 插件声明

`app.json` 的 `plugins` 里有 `expo-image-picker`，
但它**不在 `dependencies` 里，也没有任何一行代码 import 它**。
`expo prebuild` / EAS build 解析插件时会直接失败：
`Failed to resolve plugin for module "expo-image-picker"`。

两条路选一条：加依赖，或删声明。**删声明**——因为没有任何功能在用它，
为了喂饱一条配置而装一个包是本末倒置。它要的那几条权限文案
（相机、相册）`app.json` 已经在 `infoPlist` 与 `android.permissions`
里显式写了，不靠这个插件。等交付凭证拍照功能真的落地时，
依赖和插件一起加——下面这条闸门会保证它们必须一起加。

### APPB-005 闸门：`app.json` 里声明的每个插件，必须是已声明的依赖

`plugins` 数组里的每一项（字符串形式或 `[name, options]` 形式）
都要能在 `app/package.json` 的 `dependencies` 里找到。

这条和 VID-041 是同一类，但 VID-041 查的是 `import`，**查不到配置里的插件名**——
而插件解析失败同样是硬失败，且只在 `prebuild`/打包时才暴露，
也就是最晚、最贵的那个时刻。

### APPB-006 `tsconfig.json` + `npm run typecheck`，并进 CI

`strict: true`。CI 加一个 `app-typecheck` job：
`cd app && npm install && npm run typecheck`。

这条把 `app/` 从 V70 的「至少解析得过」推进到「类型是对的」，
正式了结 PRLX-041 / DSPR-042 这条挂了很久的账。

### APPB-007 顺带：VID-050 部分兑现

V71 说过三个新依赖「本环境装不了、只能做源码断言」。
现在它们装上了，版本实测：`expo-av@14.0.7`、`expo-network@6.0.1`、
`@react-native-async-storage/async-storage@1.23.1`，且 typecheck 通过。

**仍然没有验证的是「在真机上跑」**——装得上、类型对，不等于播得出。
VID-050 降级保留，不销账。

## 4. 验收点

| 编号 | 验收点 |
|---|---|
| SYNC-001 | 标签表在 `packages/core`，Web 与 App 都从 SDK 导入，全仓只有一份 |
| SYNC-002 | 服务端 `_log()` 的科目集合 ⊆ SDK 标签表；SDK 多出的键也判失败 |
| SYNC-003 | 扫描器扫不到东西时**自己失败**：科目数下界 ≥16，且三个已知科目必须命中 |
| SYNC-004 | `GET /contracts/{id}` 响应的每个键都在 `interface Contract` 里有声明 |
| SYNC-005 | Web 合约卡片显示保证金与其状态；`deposit_hold` 等 12 条有中文名 |
| APPB-001 | `cd app && npm install` 成功 |
| APPB-002 | `app/babel.config.js` 存在且用 `babel-preset-expo` |
| APPB-003 | `app/metro.config.js` 的 `watchFolders` 覆盖 `packages/core` |
| APPB-004 | `app.json` 不再声明未安装的插件 |
| APPB-005 | 插件↔依赖闸门存在，且移除依赖后会红 |
| APPB-006 | `cd app && npm run typecheck` 通过；CI 有 `app-typecheck` job |

## 5. 这一批没做的（明确记账）

- **APPB-050**：CI 的 `app-typecheck` 每次要装 1139 个包（~30s + 下载）。
  没有做依赖缓存（`actions/setup-node` 的 `cache`），第一次先让它正确，
  快慢以后再说。
- **APPB-051**：仍然没有在真机或模拟器上跑过。`npx expo start` 本环境
  起不来（要设备/模拟器连接）。**装得上 + 类型对 ≠ 跑得起来**，
  VID-050 与 PRLX-040 都还挂着。
- **APPB-052**：`app/` 没有单元测试，也没有 lint。这一批只解决
  「装得上、类型对」，行为正确性仍然只靠服务端测试与源码断言。
- **SYNC-050**：只对齐了 `Contract` 一个类型。`types.ts` 里还有二十多个
  接口，同样是手写的，同样可能漂。SYNC-004 的做法可以推广到每一个
  有稳定端点的类型，但要一个一个接——这次先把方法立住。
- **SYNC-051**：`memo` 字段是服务端写死的中文，没走 i18n。
  全站 i18n 是独立一批的事（README 里「文案 i18n 预留」还是预留状态）。
