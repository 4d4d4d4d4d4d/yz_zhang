# 基础手机助手验收 · 0.5.0

## 本轮已交付

- 正式签名非debug APK 0.5.0 已通过adb install -r更新到设备[device serial omitted]（未卸载）。构建签名、ZIP完整性、16KB对齐校验通过。
- 原生单次截屏服务ScreenCaptureService：Android 11+，用户在系统无障碍设置主动启用；仅点击开始后延迟5秒截一张。未申请读取窗口控件或执行手势能力，不监听事件内容。
- 截图缩至最长1280，JPEG最多1MiB；内存暂存60秒，到期、服务中断、销毁、下一次截屏或取出时清除暂存。受保护窗口由系统拒绝。没有写原图到文件。
- 返回App解锁后点“使用截屏”，图片附到输入框并显示预览；用户再次发送才交给本地视觉模型。离开Activity仍锁定资料库。这里不承诺字符串/系统内存可验证擦除。
- “分享草稿”：解锁后读取当前对话最后一条助手回答，原生对话框可编辑检查，再交给Android分享页。用户选择App和接收人；不等于消息发送成功，不存在发送回执。
- 新增旅行与订票核验skill、消息草稿skill。消息skill不提供web_search，执行层也拒绝绕过调用。旅行skill必须核实缺失条件、标记未核实票务数据，不能把摘要搜索或拟稿当作下单/发送。

## 验证

- native-bridge.test.cjs：锁定、忙碌、远程URL、超限图片拒绝；本地附图与草稿读取通过。属于JS逻辑测试，不是Android截屏成功证据。
- voice.test.cjs：现有语音隔离、锁定和本地识别逻辑回归通过。
- SafetyTest：写入审批、拒绝、取消、防重放、历史认证；新增消息skill联网拒绝，通过shell UID隔离测试。
- SkillAcceptance：手机本地4B实际推理，隔离临时加密资料库，测试旅行缺少条件时提问以及只拟稿不发送。初版消息输出混入控制要求，已收紧提示并复测；结果文件单独保存。

## 未完成 / 不可冒充完成

- 最后查询时，小千截屏无障碍服务未启用。跨App截屏及APK内图片分析闭环尚未实际验收。
- Android分享页和微信接收人选择尚未人工完成，没有发送消息。
- 未获得真实出行日期、人数、出发地、预算，也未获得真实接收人和消息正文；没有订票、提交订单或付款。
- 没有自动点击/控件树/页面动作验证执行器；skill提示词不能创造这些原生能力。
- Bing RSS依然存在严重相关性问题，诊断中的苏州西山岛查询出现完全无关结果。没有把搜索成功响应当作搜索质量通过；未修复为可靠票务检索。
- 电脑18091页面是设计预览。上述原生按钮位于手机安装的小千App，不在该预览页面。

## 手机验收步骤

1. 小千 → 截屏 → 打开设置 → 用户启用“小千·单次截屏”。
2. 回小千点截屏、开始；5秒内切到无个人隐私的测试页面。
3. 截取后60秒内返回小千，解锁用户自己的资料库，点使用截屏，检查预览后发送分析问题。
4. 选择消息草稿skill，明确App、接收人和正文；点击分享草稿检查内容，在目标App人工核对接收人再发送。不要把分享页打开当成已发出。

Android API参考：https://developer.android.com/reference/android/accessibilityservice/AccessibilityService#takeScreenshot(int,java.util.concurrent.Executor,android.accessibilityservice.AccessibilityService.TakeScreenshotCallback)

## 本轮复测结论

- 旅行条件核实：17.985秒，询问出发地、日期、人数、预算，无工具调用；只证明条件收集，不代表行程完成。
- 消息初次提示优化仍漏掉“请忽略”，记录见skill-acceptance-refined.json，未判为通过。
- 再增加明确正文逐字保留要求，并把验收输入正文以引号界定：8.600秒，严格返回“本地助手消息能力测试，请忽略。”，工具列表为空。已做精确文本断言。该单例通过不代表自由表达都能保真，原生分享前编辑核对仍保留。
- 最终结果skill-acceptance-final.json；最终构建已再次安装成功。此处依旧没有真实发送回执。

## 最新界面验收阻塞

2026-10-18 最新复查：OPPO投屏授权已经完成，CUA可见真实手机桌面，并通过桌面搜索中的“小千·内测”图标启动应用。进入小千后投屏显示“请在手机操作”；代码确认MainActivity启用了FLAG_SECURE，未关闭此保护。ADB确认版本0.5.0-private-beta / versionCode 5，应用进程存在。此结果只证明应用已启动，不证明模型加载或推理成功。

本轮开始查询时小千ScreenCaptureService仍未启用。后续需用户在手机内操作“截屏 → 打开设置”，自行确认“小千·单次截屏”授权；完成后才能验收跨App截图。真实行程信息和消息测试接收人、正文仍未收到明确答复。本轮没有提交订单、发送消息、更改系统权限或绕过受保护窗口。

后续更新：用户已确认开启。CUA看到“无障碍 → 通用 → 已下载的应用 → 小千·单次截屏”显示“已开启”；ADB的enabled_accessibility_services及dumpsys accessibility均包含该服务。授权和系统服务注册已确认，尚未取得实际captureOnce成功及APK内视觉回答的证据。小千自身窗口仍受FLAG_SECURE保护，需用户在手机内触发截屏、解锁并提交分析；不能将授权成功当作截图分析验收通过。

## 0.5.1 启动故障修复（2026-10-19）

- 用户反馈模型进程启动失败。Android crash buffer 精确记录 linker 拒绝加载 libggml-opencl.so 的依赖 libOpenCL.so；旧APK误用了带硬依赖的Snapdragon运行库，CPU参数无法避免链接阶段失败。
- 改用官方 b11527 Android ARM64 通用运行库，下载SHA-256与GitHub release资产digest一致：1146f95ea77bc70e8653aeef76e89d6f362094eb27ab5949607c38158bc4c56e。仅打包基础推理库和动态CPU变体，不附带OpenCL/Hexagon/RPC后端。应用版仍是CPU推理；本次不声称恢复NPU。
- 0.5.1 / versionCode 6 正式非debug签名APK已覆盖安装成功。安装包完整性、签名、16KB对齐通过；tests/check-apk-runtime.py验证每个ELF依赖均由包内库或允许的Android公共库满足。
- 安装后的二进制 --version 成功。使用安装目录中相同二进制，在shell UID以512上下文加载公开4B模型，5秒后health=ok；测试进程已结束、临时端口转发已删除。详见apk-cpu-runtime-smoke.json。此项不替代应用UID和WebView闭环验收。
- 截屏状态改为独立文本，避免模型服务状态轮询遮盖；截图成功和系统截图失败新增Toast反馈。模型异常退出显示退出码。原生桥接与语音JS回归通过。
- 覆盖安装后尚待用户重新打开小千。投屏连接已断开，未绕过FLAG_SECURE；实际应用模型就绪、跨App截图成功、图片回答仍待验证。

## 0.5.2 前台推理防熄屏

用户提交图片后未见回答。设备日志确认熄屏后OPPO Hans冻结应用和模型；亮屏后health恢复ok，但用户反馈界面已回初始状态。代码检查发现MainActivity.onStop会锁定资料库、取消/清空任务并清空WebView，此行为可解释页面恢复但无回答，未读取用户私有对话来断言具体任务结果。

新增仅在Activity可见且存在未结束任务时设置FLAG_KEEP_SCREEN_ON，任务结束或离开立即清除；不获取后台唤醒锁，不绕过锁屏、后台取消和资料库保护。新增前台状态说明和同一Activity返回时的中断提醒（进程重建后此内存提示不保留）。0.5.2构建/签名/对齐、ELF依赖、桥接及语音回归通过；实际图片回答和自动熄屏防护仍需真机提交复测。

## 临时投屏调试构建 0.5.3

用户明确要求暂时解除黑屏保护方便调试，后续恢复。build-apk.py新增--screen-debug选项，仅对构建目录的MainActivity移除FLAG_SECURE；源文件与默认构建仍保留保护。独立产物qwen-local-screen-debug.apk（versionCode 8，非debuggable、原签名）已覆盖安装成功，清单记录screen_protection=false。未修改加密、锁定或HTTP认证。CUA已实际看到小千原生按钮与截屏服务就绪状态，投屏不再全黑。后续恢复应构建默认正式APK并覆盖安装。
