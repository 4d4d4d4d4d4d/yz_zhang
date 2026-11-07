
# 128 端侧隐私沙箱：本机助手、量化小模型、原文不上云、同步前脱敏

> 状态：本批实现（V158）。编号 SBX-100~110；顺带做完 INF-110 的一半（端上独立验算影响力证明，BACKLOG V159）。
> 来源：用户 2026-10-14：「需要一套本地隐私性沙箱模式，能够在端侧手机上跑量化小模型从而信息不上传云端，能够完成一些基本 agent 助理的操作。」VISION 1.9 / V-19；BACKLOG V158。
> 只增不减：沙箱**默认关着**，关着时一切照旧；云端助手的接口、知识库、工作台都不改，只是开着沙箱时多一道拦截；
> `get_current_user` 只多一个检查（只对开着沙箱的人、只对 14 个接口生效）。

## 0. 要解决的问题

助手要帮人处理的恰恰是最私密的东西：纪要、合同、报销单、聊天记录。现在所有助手都在云端：
问一句就把原文发到服务器，再可能转给模型供应商。有的人（律师、财务、OPC 自己的客户资料）因此根本不敢用。

## 1. 业界怎么做（带来源链接）

- **系统级端侧模型**：Apple Foundation Models 框架把端侧模型（约 4K 上下文）留给轻量、对延迟与隐私敏感的任务，重活才交给 Private Cloud Compute
  （<https://developer.apple.com/foundation-models-framework/>，WWDC26 <https://developer.apple.com/videos/play/wwdc2026/8016/>）；
  Android 的 Gemini Nano 跑在 AICore 系统服务里，AICore 自己不能直接联网（<https://developer.android.com/ai/gemini-nano>）。
  共同点：**端侧做小事、原文不出设备、要更强的能力必须显式换到云端**——这里照做：沙箱开着就只在本机，关掉才用云端助手，不悄悄回退。
- **React Native 上跑量化小模型**：llama.rn（llama.cpp 绑定，GGUF 量化模型，支持工具调用与语法约束输出，<https://github.com/mybigday/llama.rn>）、
  Callstack 的 `@react-native-ai/llama`（<https://github.com/callstackincubator/ai>）、Software Mansion 的 react-native-executorch；
  社区实测 3B 级 Q4 模型在旗舰机上约 18~25 token/s（<https://huggingface.co/blog/llm-inference-on-edge> 一类的整理，二手数据，仅作量级参考）。
  这里把运行时抽象成 `LocalModel` 接口，原生构建注入；SDK 与界面不依赖某一个运行时。
- **模型文件完整性**：llama.rn 的预编译库下载后按 SHA-256 校验；模型文件同理——平台目录只登记「地址 + sha256 + 大小 + 许可证 + 最低内存」，手机直接下载并校验，对不上就删。

## 2. 数据

| 表 / 存储 | 说明 |
|---|---|
| `users.privacy.sandbox` / `sandbox_since` | 开关与起始时间（服务端只存这一个标记，不存任何本机内容） |
| `sandbox_models`（迁移 `c1d220260019`） | 端侧模型目录：标识、名称、参数量、量化、格式、大小、sha256、https 地址、许可证、最低内存、语言、适合的本机技能、状态（草稿 / 已上架 / 已下架）、登记人、审核人 |
| 浏览器 `localStorage` / 手机 `AsyncStorage` | 沙箱开关的本机副本、本机笔记——**只在这台设备上** |

## 3. 接口与 SDK

| 编号 | 内容 |
|---|---|
| SBX-101 | `GET/PUT /users/me/sandbox`：开关；打开时先在本机生效（拦截立刻起作用）再告诉服务端，关闭时服务端成功了才在本机关；服务端记着开着而本机没开时，以开着为准 |
| SBX-102 | SDK `ClientOptions.sandbox`：开着时 14 个「把原文交给 AI」的请求**在发出之前**就抛 `sandbox_cloud_ai_blocked`，一个字节都不发；清单 `CLOUD_AI_ENDPOINTS` 与服务端 `CLOUD_AI_ROUTES` 双向一致 |
| SBX-103 | 服务端兜底：开着沙箱的人调用这 14 个接口一律 409（给老客户端与绕过客户端的）；服务端替他跑的 AI（工作台拆清单、已建好的使命规划）通过 `gateway_for` 只用模板，**云端模型一次都不被调用** |
| SBX-104 | 本机助手（`packages/core/src/sandbox.ts`）：摘要、拆成清单、抽出待办、改写得正式一点、起草回复；一句话指令路由到技能；**要动钱、签署、发布、对外发送的一律不做**；有端侧模型用模型，模型出错（内存不够被杀）如实退回本机规则并写明「不是模型」，不悄悄换成云端 |
| SBX-105 | 脱敏 `redact`：手机号、身份证号、银行卡号、邮箱、车牌；同步到云端知识库前给人看「发出去的是这份、遮掉了什么」，**勾选确认后才发** |
| SBX-106 | 端侧模型目录：`GET /sandbox/models`（已上架的）；后台登记 / 修改（只限草稿）/ 上架（四眼：登记的人不能批；必须有 64 位 sha256、https 地址、大小、许可证、最低内存）/ 下架（写原因，进审计）；SDK 纯 TS 增量 `Sha256` 与 `verifyModelChunks` 供手机分块校验几百 MB 的模型文件；`canRunModel` 按内存与存储如实说跑不跑得动 |
| SBX-107 | 本机这个文件不联网：`sandbox.ts` 不引用 client、不调 fetch / XHR / WebSocket（静态扫描钉住） |
| INF-110（一半） | `influenceLeaf` / `verifyInfluenceProof`：与服务端逐字节一致地算叶子，沿 Merkle 路径算到锚定的树根；影响力页（Web 与 App）显示「本机验算通过 / 不通过」，不再只信服务端的 `verified` |

错误码（`i18n.ts`）：`sandbox_cloud_ai_blocked`、`sandbox_model_exists`、`sandbox_model_not_draft`、`sandbox_model_four_eyes`、`sandbox_model_incomplete`、`sandbox_model_bad_skill`。

## 4. 两端

- **Web** `/sandbox`（个人中心入口）：开关、本机助手（浏览器里用本机规则）、本机笔记、同步前脱敏与确认、端侧模型目录；后台「端侧模型目录」一块。
- **App**「我的 → 隐私沙箱」：同样几块；装了端侧模型（`setLocalModel` 注入）就显示模型名并用它，没有就用本机规则。
- 两端的 SDK 客户端都接上了 `sandbox` 开关（Web 读 localStorage，App 启动时从 AsyncStorage 恢复）。

## 5. 隐私、授权与边界

- 本机助手的输入与输出从不经过服务端；服务端只知道「这个人开着沙箱」。
- 同步只发脱敏后的结果；人名、地址这类规则认不全的，界面明说「请你自己看一遍」。
- 红线不变：钱、签署、申报、发布、对外发送，本机助手只拒绝并指向人工确认。
- 模型文件不经平台服务器，平台只登记、审核与下架；下架后列表里看不到（已下载的由 App 在下次启动时提示删除——见「没做的」）。
- 注销：`privacy` 清空（既有处置）；本机数据随设备，App 卸载即删。

## 6. 闸门与红验

服务端 9 处、SDK 2 处、Web 2 处、App 2 处变异全部变红：

| 闸门 | 红验 |
|---|---|
| 14 个接口在沙箱下全部 409 | 去掉 `get_current_user` 里的检查 → `test_every_cloud_ai_endpoint_refuses…`（14 条参数化）红 |
| 清单两端一致、名字像 AI 的写接口都在清单里 | 从服务端清单删一条 → `test_cloud_ai_list_matches…` / `test_every_listed_route…` 红 |
| 服务端替他跑的 AI 不出网 | 工作台改回全局网关 / `gateway_for` 不看沙箱 → `test_server_side_ai…never_reaches_the_model` 红 |
| 四眼、sha256、https、只列已上架 | 各去一处 → `test_model_catalog_four_eyes…` 红 |
| 开关起点 | 不记 `since` → `test_toggle…` 红 |
| SDK 发请求前拦截 | 去掉拦截 → `sandbox.test.ts` 红；Merkle 父节点不排序 → 证明验算红 |
| 同步发的是脱敏后的 | Web / App 改成发原文 → `Sandbox.test.tsx` / `sandbox.test.tsx` 红 |
| 自己登记的不能上架 | 后台显示上架按钮 → `Sandbox.test.tsx` 红 |
| App 客户端真接上开关 | `isSandbox` 恒为 false → `sandbox.test.tsx` 红 |
| 本机文件不联网 | 静态扫描 `sandbox.ts` |
| 真浏览器 | `e2e_web.py`：打开沙箱 → 真服务端记住 → 抽待办 → 同步预览里手机号已遮掉 → 关掉 |

## 7. 没做的

- **SBX-110 原生推理运行时接入与真机验收**：`LocalModel` 的 llama.rn（或 ExecuTorch）适配要 Expo 开发构建（New Architecture）与真机测速、发热、内存，记作「外」（需要真机与原生构建流水线）。
  在那之前 App 用本机规则，界面如实写明。
- **SBX-111 手机端模型下载与断点续传**：要 `expo-file-system` 的后台下载；校验函数（分块 sha256）已经在 SDK 里，排进 BACKLOG V160。
- **SBX-112 浏览器端 WebGPU 小模型**：桌面浏览器可以跑 WebLLM 一类的端侧模型，排进 V160 一起评估。
- 已下架模型在手机上的清理提示：随 SBX-111 一起做。
- 公链锚定（INF-110 的另一半）仍是「外」。
