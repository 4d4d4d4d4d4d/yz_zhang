# 小千：Android 本地模型助手

这是截至 2026-11-09 的工程交接快照，版本 `0.5.19`。主要目标是在 Android 手机上运行 Qwen3.5-4B，并通过本机工具完成聊天、图片分析和有限的跨应用操作。**当前仍是开发验证阶段，日常 Agent 六项业务尚未全部通过，不能视为商业发行版。**

## 当前能力

- 独立 Android APK，`org.qwen.local`；当前 APK 使用 llama.cpp b11527 的 ARM64 CPU 路径。
- Qwen3.5-4B Q4_0 与可选 F16 视觉投影器；模型文件按固定大小和 SHA-256 校验后导入。
- 聊天、加密笔记、上下文压缩、用户确认的偏好记录、获准后的网页摘要检索。
- 原生单次截屏 → 本地图片分析链路已有真机验证；尚无通用视觉操作闭环。
- 调试版可选择携程查询、Telegram 收藏夹固定测试消息、饿了么/淘宝闪购浏览搜索。
- 跨应用动作由本地模型调用应用自己的 Accessibility 执行器；ADB仅用于部署、启动测试及观察。
- 执行回执依据实际工具结果生成；近期动作状态加密持久化。发送尝试与送达严格分开。

## 验证边界

| 项目 | 当前结论 |
| --- | --- |
| 携程 | 已有首页 → 机票 → 查询 → 读取列表 → 返回小千的记录，约307秒；未完成完整航班条件核验或订票 |
| Telegram | 收藏夹固定正文发送代码已接入；发送标记核验为空，尚无真实发送/送达通过证据 |
| 外卖 | 闪购已安装；页面授权和登录状态阻塞过测试，搜索、规格、加购、结算未通过 |
| 回复消息、查快递、购物比价、小程序点单 | 未通过完整端到端验收 |
| NPU | `native/`保留shell环境实验；不能把历史HTP数据当成当前APK的能力 |
| 语音 | 浏览器实验能力；APK没有已验收的原生语音唤醒服务 |

最新交接见 [docs/HANDOFF.md](docs/HANDOFF.md)。`reports/*.md` 是历史报告，日期和当时版本有效；其中引用的真机截图、原始日志和结果文件没有上传。历史命令行说明见 [docs/LEGACY-CLI.md](docs/LEGACY-CLI.md)。

## 构建与运行

当前使用自定义构建脚本，尚未提供从空白环境一键安装全部依赖的流程。先按 [android/README.md](android/README.md) 准备 Android SDK、JDK、D8、Zig 和 llama.cpp ARM64 CPU 动态库。

```sh
export QWEN_JAVA_BIN=/path/to/jdk/bin
python3 build-apk.py
# 仅供本机调试：关闭截屏保护和后台/空闲自动锁库；首次仍需用户解锁
python3 build-apk.py --screen-debug --keep-vault-unlocked
```

发布默认保留屏幕保护及自动锁库，应用操作入口目前只在上述调试模式开放。不要把调试包当作隐私保护已验收的发行包。

模型、SDK、第三方运行库、APK、签名材料、资料库和原始真机证据均不在仓库中。模型元数据见 `manifest.json`，下载脚本为 `download-model.py`、`download-vision.py`；下载模型不会自动准备完整构建工具链。

部署旧shell服务前设置 `QWEN_PHONE_SERIAL`（可用 `adb devices` 查看），脚本不再预设个人设备序列号。新签名材料无法覆盖安装另一签名的同包名APK；请自行安全保管原签名，不要通过卸载来冒险保留数据。

## 目录

- `agent/`：模型调用、工具调度、加密资料库、skills及WebView界面。
- `android/`：Activity、前台服务、Keystore绑定、截屏和应用执行器。
- `native/`：模型子进程生命周期与实验性NPU staging代码。
- `tests/`：权限边界、控件引用、执行记录、截屏交接、界面及设备集成测试。
- `design/`：界面样式；独立预览页面不代表手机实时状态。

## 本地检查

部分Python测试仍依赖本机JDK路径，`ui-audit.py`另需 `tools/json.jar`。不要把设备集成测试随意运行在有个人数据的正式资料库上。

```sh
python3 tests/task-scope.py
python3 tests/query-target.py
python3 tests/query-policy.py
python3 tests/ui-audit.py
python3 tests/capture-delivery.py
node tests/native-bridge.test.cjs
node tests/conversation-display.test.cjs
node tests/voice.test.cjs
```

当前数据记录以AES-GCM加密、口令派生并绑定Android Keystore；尚未完成独立安全审查、备份恢复和密钥丢失恢复。详见交接文档，不承诺绝对隐私安全或商业就绪。
