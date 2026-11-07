# 161 多模态智能体操作其他 App（无 agent 接口时）

> 状态：本批实现（V190）：平台侧 XAPP-001~010；端上执行器 XAPP-011~014 为「外」；计划生成 XAPP-015 本批实现（V191）；云端看屏幕 XAPP-016 欠（随执行器）。
> 来源：用户 2026-10-15「支持通过多模态智能体能够直接操作其他app吗，在其他app不提供agent的通信api的情况下」（VISION 1.12）；BACKLOG V190。
> 只增不减：开放 API、Webhook、机器授权（MachineMandate）、端侧隐私沙箱都不变；这是新的一条能力线。

## 0. 要解决的问题

- 用户要办的事常常跨好几个 App：在平台上接了一单，要去地图 App 查路线、去聊天 App 回客户、去记账 App 记一笔、去政务 App 查一项政策。这些 App 大多**不提供给智能体用的接口**。
- 现在平台的智能体只能动平台自己的数据（任务、笔记、待办）和本机数据（端侧沙箱）；出了平台就到头了。
- 「看着屏幕替人点」技术上已经可行，但它碰的是用户整部手机：别的 App 的聊天、验证码、银行卡。做不好就是隐私事故，或者违反对方 App 的条款。

## 1. 业界怎么做（带来源链接）

| 做法 | 例子 | 说明 |
|---|---|---|
| 系统无障碍服务 + 多模态模型（Android） | 智谱 AutoGLM（<https://xiao9905.github.io/AutoGLM/>）、字节 UI-TARS（<https://github.com/bytedance/UI-TARS>）、Google Android 无障碍服务（<https://developer.android.com/guide/topics/ui/accessibility/service>） | 读控件树、模拟点击和输入；读不到控件时截屏让模型识别。Google Play 对无障碍权限有专门的申报与审核政策（<https://support.google.com/googleplay/android-developer/answer/10964491>） |
| 应用开放的动作（iOS） | App Intents、快捷指令（<https://developer.apple.com/documentation/appintents>）、URL Scheme | iOS 不允许一个 App 读取或操作另一个 App 的界面；只能调用对方主动暴露的动作 |
| 桌面电脑操作 | Anthropic computer use（<https://docs.anthropic.com/en/docs/agents-and-tools/computer-use>）、OpenAI Operator | 截屏 + 坐标操作 + 系统无障碍接口，在本机或沙箱虚拟机里执行 |
| 深链 / Intent | Android Intent、各 App 的 URL Scheme、微信小程序跳转 | 最稳：不看屏幕，直接打开到某个页面或带参数的动作 |

共同的做法：**每一步可见、可叫停；敏感动作要人确认；执行记录留存**。

## 2. 数据

| 表 | 字段 |
|---|---|
| `xapp_grants`（操作授权） | 用户、执行器设备、允许的目标 App（包名 / 应用标识）白名单、允许的动作类别（打开、阅读、填写、点击、导航）、有效期、是否允许云端看屏幕（默认否） |
| `xapp_runs`（一次执行） | 用户、目标、计划（步骤列表）、状态（计划中 / 等确认 / 执行中 / 已叫停 / 完成 / 失败）、执行器类型（android / desktop / ios_shortcut / mock）、开始与结束时间 |
| `xapp_steps`（每一步） | 第几步、意图（「打开地图搜索某地址」）、通道（api / deeplink / a11y / vision）、要不要人确认、确认人与时间、结果、执行前后的屏幕摘要（只存脱敏文字摘要，不存截图原图） |

## 3. 规则与接口（平台侧，V190）

| 编号 | 内容 |
|---|---|
| XAPP-001 | 授权：用户在自己的设备上开一个授权，写明哪些 App、哪些动作、到期时间；没授权的 App 一律拒；授权随时可撤，撤了正在跑的立刻停 |
| XAPP-002 | 计划：智能体先出计划，每步写「在哪个 App、做什么、用哪个通道、预期结果」；通道按 API → 深链 → 控件树 → 截屏识别的顺序选，能用前面的就不用后面的 |
| XAPP-003 | 红线拦截：涉及付款、转账、签署、发布、对外发消息、改密码或安全设置、删除数据的步骤，一律标「必须人确认」，由用户在屏幕上亲手点；智能体不能代点 |
| XAPP-004 | 逐步确认与叫停：用户可选「每步都确认」或「只确认红线步」；任何时候一键叫停，执行器在当前步之后不再动 |
| XAPP-005 | 隐私：屏幕内容默认只在本机由端侧模型处理（与 128 号沙箱同一套）；要用云端模型看屏幕，必须在授权里单独打开并每次提示；服务端只收脱敏后的文字摘要 |
| XAPP-006 | 执行记录与回放：每步的意图、通道、结果、确认人进记录；用户可回看；记录随注销删除、进数据导出 |
| XAPP-007 | 统一执行器协议：`拿到下一步 → 执行 → 回报结果`；Android 无障碍执行器、桌面执行器、iOS 快捷指令、模拟执行器（测试用）都按这个协议对接 |
| XAPP-008 | 合规边界：只为本人、在本人设备上、对白名单里的 App 操作；不做批量、不托管别人的账号、不绕过验证码与风控；被目标 App 明确禁止自动化的，不进白名单 |
| XAPP-009 | 失败与漂移：目标 App 改版导致找不到控件时停下并说清卡在哪一步，不盲点；同一步连续失败两次就交还给人 |
| XAPP-010 | 成本与限额：每次执行的步数上限、每天次数上限；用云端模型看屏幕的计入助手月度成本上限（REL-110） |

## 4. 两端

- **App**：「我的 → 跨 App 助手」：授权管理（目标 App、动作、到期）、发起一次任务、看计划、逐步确认、一键叫停、执行记录回放。Android 上由原生执行器真正去点；iOS 上只列出可用的快捷指令动作。
- **Web**：执行记录与授权的查看、撤销；桌面执行器下载与配对（执行器本身是本机程序）。

## 5. 隐私、授权与边界

见 XAPP-003、005、008。另外：
- 执行器以用户自己的身份操作，平台不保存目标 App 的账号密码。
- 截图原图不出设备；服务端只存脱敏的文字摘要。
- 这条能力默认关闭，用户要主动开启，界面上一直有「正在替你操作」的标识。

## 6. 闸门与红验

V190 实现（`server/app/modules/xapp/`，接口 `/api/v1/xapp/*` 共 10 个，表 `xapp_grants` / `xapp_runs` / `xapp_steps`，迁移 `c1d220260033`）：

| 闸门 | 测试 | 红验（故意改坏 → 变红） |
|---|---|---|
| 红线动作不能授权（XAPP-001/003） | `test_grant_rejects_red_line_actions_and_bad_apps` | 去掉红线判断 → 红 |
| 计划只能用授权里的 App 与动作，云端看屏幕默认关（XAPP-001/005） | `test_plan_must_stay_inside_the_grant` | 去掉白名单判断 → 红；去掉云端看屏幕判断 → 红 |
| 红线步只「带人到那个页面」，执行器不能代点；确认后算「你已亲手完成」（XAPP-003） | `test_executor_walks_the_plan_and_red_line_steps_go_back_to_the_person`、`test_red_line_step_after_confirm_is_a_handoff_not_an_execution` | 红线标记恒为假 → 红；红线步改成派发 → 红 |
| 每步确认模式等每一步（XAPP-004） | `test_each_mode_waits_for_every_step` | 去掉待确认判断 → 红 |
| 连续失败两次交还给人；回报当场脱敏（手机号、6 位以上数字）（XAPP-005/009） | `test_two_failures_hand_the_run_back_and_results_are_scrubbed` | 去掉失败计数 → 红；跳过脱敏 → 红（本批把测试加强成「当场」检查，原先被第二次回报盖掉而漏网） |
| 叫停、撤销授权当场停，此后不再派发（XAPP-001/004） | `test_stop_and_revoke_stop_everything` | 去掉非执行中的拦截 → 红；撤销时不停正在跑的 → 红（本批加强：撤销后立刻查记录，不靠下一次拿步骤） |
| 授权过期，下一步就停 | `test_expired_grant_stops_the_run_at_the_next_step` | 去掉过期判断 → 红 |
| 步数上限与每天次数上限（XAPP-010） | `test_limits` | — |
| 记录进数据导出、随注销删除（XAPP-006） | `test_records_are_in_export_and_erased_on_deletion` | 注销时不删授权 → 红 |
| 响应形状与 SDK 类型一致 | `test_every_xapp_response_matches_the_sdk_types` | — |
| 对象级授权 | `test_object_level_authz.py`：`/xapp/` 归本人，别人的编号 404 | — |
| 两端 | App `xapp.test.tsx`（3 条：授权、红线步亲手完成、叫停、示例执行、模拟执行器试跑）；Web `Xapp.test.tsx`；SDK `xapp.test.ts`（`driveXappRun` 执行器循环）；真浏览器 `e2e_web.py` 走 `/xapp` | 去掉红线提示（App、Web 各一处）→ 红 |

V191 实现 XAPP-015（`server/app/modules/xapp/planner.py`，接口 `POST /xapp/plan`，只出草稿不发起）：

| 闸门 | 测试 | 红验 |
|---|---|---|
| 规则计划与本机计划是同一个算法：两边读同一份例子文件 `packages/core/src/xapp-plan-cases.json`（8 个例子，规则表也在里面，必须等于服务端） | `test_shared_cases_match_the_server_rules_both_ways`；SDK `xapp.test.ts` | 服务端去掉长词优先 → 红；SDK 去掉 App 名占位 → 红 |
| 通道按 API → 深链 → 控件树 → 屏幕识别的顺序挑；红线步自动标出，发起后要本人确认 | `test_rules_plan_follows_channel_order_and_marks_red_line` | 打开改挑最后一个通道 → 红 |
| 「支付宝」里的「支付」不是付款；没授权的动作列出来、草稿标成不能直接发起 | `test_app_name_is_not_an_action_and_missing_actions_are_listed` | 去掉 App 名占位 → 红；不算缺的动作 → 红 |
| 只能用自己的、生效中的授权 | `test_plan_needs_an_active_grant_of_my_own` | 不查授权归属 → 红 |
| 隐私沙箱里这个接口被拦下（目标原文不上云），目录带规则表让手机在本机出 | `test_sandbox_blocks_the_plan_endpoint_and_the_catalog_carries_the_rules`；`test_sandbox.py` 两端清单一致 | 从云端 AI 清单里去掉 → 红 |
| 模型出的计划不能越过授权：不在授权里的 App 丢掉、不认得的动作丢掉、红线由服务端判、乱写的通道按规则挑 | `test_model_plan_cannot_widen_the_grant` | 不查 App → 红；红线跟着模型走 → 红 |
| 模型出错或给的全不能用：退回规则并写明 | `test_model_failure_falls_back_to_rules_visibly` | 不写明 → 红 |
| 模型调用用结构化输出、调用前先还数据库连接（CONC-067） | `test_anthropic_plan_uses_structured_output_and_releases_the_connection` | — |
| App：出计划、红线步写明「你亲手完成」、照草稿发起；沙箱开着就在本机出、不发请求 | `app/xapp.test.tsx` | — |

改规则表时：改 `planner.py`，用它重新生成例子文件里的 `rules` 与每个 `expect`（161 号 spec 第 6 节），再让 SDK 的 `planXappSteps` 跟上——两边测试都过才算改完。

执行器协议在共享 SDK：`driveXappRun(client, runId, {perform, handoff})` 循环「拿下一步 → 执行 → 回报」，遇到等确认、交还给人、叫停就停下。App 上「用模拟执行器试跑」就是用它，不碰任何 App。

## 7. 没做的

- **XAPP-011 Android 无障碍执行器**：原生模块，需要 Expo 开发构建与真机验收；Google Play 无障碍权限申报（外）。
- **XAPP-012 桌面执行器**：本机程序（Windows / macOS），需要签名与分发（外）。
- **XAPP-013 iOS 快捷指令动作包**：需要真机与 App Store 审核（外）。
- **XAPP-014 端侧屏幕理解模型**：能在手机上跑的界面理解小模型，接进端侧模型目录（与 SBX-110 一起，外）。
- ~~**XAPP-015 智能体出计划**~~ → **已做**（V191，本 spec 第 6 节）。规则表现在只认 8 个常见 App 的名字与通道；更多 App 的通道表（尤其哪些 App 有公开深链）要随真机执行器一起补（XAPP-017，随 XAPP-011）。
- **XAPP-016 云端看屏幕接口与成本**：平台还没有「把屏幕摘要交给云端模型识别」的接口；做的时候必须进端侧沙箱的云端 AI 名单、每次提示、计入助手月度成本上限（REL-110）。依赖端上执行器，随 XAPP-011/012 一起做（欠）。
- Web 上桌面执行器的下载与配对、iOS 上列出可用的快捷指令动作：随 XAPP-012 / XAPP-013（外）。
