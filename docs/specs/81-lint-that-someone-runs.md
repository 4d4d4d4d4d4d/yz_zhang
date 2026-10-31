# 81 有人在跑的 lint（APPB-052b / APPB-050）

> 状态：本批实现（V106）
> 依赖：47 号（共享契约与 App 装不上那件事）、69 号（App 单元测试）

## 0. 探针

台账里 `APPB-052b` 写的是「App 没有 lint」。查一遍发现说轻了：

```
package.json      scripts: ['test', 'dev:web', 'build:web']
web/package.json  scripts: ['dev', 'build', 'preview', 'test']
app/package.json  scripts: ['start', 'android', 'ios', 'typecheck', 'test']
```

没有配置、没有依赖、没有脚本——**全仓一处 lint 都没有**。
（我自己在排期时写的是「web 有 eslint 而 app 没有」，那句是错的。）

而 `web/src/pages/Square.tsx` 里躺着这一行：

```ts
// eslint-disable-next-line react-hooks/exhaustive-deps
```

**一条为不存在的检查写下的豁免注释。**

这一路反复出现的形状是「写下来的承诺没有人核对」（V96 的「在管理后台做」、
V99 的「必须换人」、V101 的 `can_invoice`、V103 的 `SUPPORT_SLA_HOURS`）。
这一条是它的**反面**：豁免了一个没有人在检查的东西。
它比前者更隐蔽——前者让人以为「有人做了」，后者让人以为「有人看过并决定放过」，
而事实是从来没有人看。

## 1. 规则怎么选

原则与闸门一致：**只开会红在真问题上的那些。**

一个满口风格警告的 lint 会被人用 `--quiet` 绕过，或者干脆不跑——
**那比没有 lint 更糟，因为它让人以为有人在看。**

| 开着 | 为什么它会红在真问题上 |
|---|---|
| `react-hooks/rules-of-hooks` | 条件里调 hook 会让 React 的状态错位，症状是「偶发的状态串了」 |
| `react-hooks/exhaustive-deps`（warn） | 漏依赖 = 闭包里是旧值，界面上表现为「点了没反应」「显示的是上一次的数据」 |
| `no-unused-vars` | 常是「改了一半」的残留：删掉的调用留下的 import 与参数 |
| `eqeqeq` | `'' == 0` 为真，金额与状态判断上出过事 |
| `no-empty`（允许带注释的 catch） | 空 catch 把错误吞掉；这个仓里有意吞的地方都写了注释 |

刻意关掉的两条各写了理由（`no-explicit-any`：边界处的响应逐个建类型是
`SYNC-050` 那条线的事；`no-non-null-assertion`：测试与 mock 里到处都是，
报它等于报测试）。**关掉要写理由**——否则半年后没人知道这是想清楚了不要，
还是当时懒得修。

## 2. 第一次跑出来的东西

```
✖ 21 problems (19 errors, 2 warnings)
```

分三类：

1. **我的配置的错**：`babel.config.js` / `metro.config.js` / `jest.setup.js`
   是跑在 Node 里的 CommonJS，`require` / `module` / `__dirname` 在那里是对的。
   给它们单独一块，**而不是把规则关掉**——关掉会连产品代码一起放过。
2. **死导入 7 处**：6 个 web 页面与 `BlogEditor` 里的 `ApiError`、
   `VideoFeed` 里的 `useCallback`。都是重构留下的。
3. **两处漏依赖**（真问题）：`Discover` 的 `load` 与 `BlogEditor` 的 `loadDrafts`
   都是 `useEffect(() => { void load(); }, [])`。这两个闭包捕获的是
   **首次渲染的 `client`**——换 token / 换 baseUrl 之后，它们还在用旧的那个。
   修法是 `useCallback` 包住并进依赖，**不是再加一条豁免注释**。

## 3. APPB-050 CI 装 1139 个包

`app-typecheck` 这个 job 的 `setup-node` **没开 npm 缓存**——1139 个包每次
重新下载。加上 `cache: npm` 与 `cache-dependency-path: app/package-lock.json`
（键要跟着 app 自己的 lockfile 走，它不在根 workspaces 里）。

**lint 不在这个 job 里跑**：lint 是纯静态的，不需要 react-native 在位，
而根上的 `npm run lint` 已经把 `app/*.tsx` 一起扫了。这个 job 每多一个依赖
都要多下一次——那正是 APPB-050 在说的事。

`app/package.json` 里**刻意不放** lint 脚本：它没装 eslint，留一条跑不起来的
脚本比没有更糟（`command not found` 会让人以为是环境坏了）。

## 4. 闸门

| 内容 | 为什么 |
|---|---|
| lint 的范围必须含三个源码树 | 少一个，那一端就是自由的 |
| CI 里真的跑，且排在测试前面 | 几秒钟就失败，省掉后面几分钟 |
| 不许 `\|\| true` / `--quiet` / `continue-on-error` 绕过 | 绕过之后它只是个装饰 |
| 每条 `eslint-disable` 引用的规则必须**真的被配置着** | 否则又是一条没人核对的豁免 |
| 关掉的规则必须写明理由 | 值是原因，不是开关（V90） |
| `app/` 里不许有 lint 脚本 | 它没有 eslint 依赖，那条脚本跑不起来 |

写这几条时改过一次判据：第一版断言「CI 里至少两处 `npm run lint`」，
照着它写就得在 App job 里再装一份 eslint——而那与 APPB-050 直接冲突。
**闸门要钉住目的（三个端的源码都被扫到），不是钉住某一种做法。**

## 5. 验收点

| 编号 | 验收点 |
|---|---|
| APPB-052b | 全仓 lint 干净（exit 0） |
| APPB-052b | lint 范围含 core / web / app 三处 |
| APPB-052b | CI 跑 lint 且排在测试前，没有被绕过 |
| APPB-052b | 豁免注释引用的规则真的被配置着 |
| APPB-052b | 关掉的规则写明了理由 |
| APPB-050 | App job 开了 npm 缓存，键跟着 app 的 lockfile |

## 6. 这一批没做的

- **没开类型感知规则**（`no-floating-promises`、`no-misused-promises` 等）。
  它们要 `parserOptions.project`，会让 lint 从几秒变成几十秒，而且要给
  三个 tsconfig 各配一遍。这两条本来是最能抓住真问题的
  （这个仓里 `void promise` 的写法到处都是），值得单独一批。
- **没加 prettier / 格式化**：风格统一是另一回事，而且格式化会产生一次
  全仓 diff，把它和逻辑改动混在一起会让审阅变成不可能。
- `exhaustive-deps` 目前是 **warn 不是 error**：先让它不挡 CI，
  等把现有代码里剩下的漏依赖清完再升级成 error。
- **APPB-050 只做了缓存**，没做「按 workspace 拆 job」或 `npm ci`。
  换 `npm ci` 要先保证两个 lockfile 与 package.json 始终同步，
  那本身该有一条闸门。
