# APK 独立应用验收（2026-10-17）

## 已确认

- 用户确认安装成功，系统 pm path 查到 org.qwen.local；此后相同签名 debug 覆盖安装成功。原“解析包”问题目前未再出现，但没有证据把原因归结为某一个打包修改。
- 0.4.0 正式包已成功复制到手机 Download/小千内测.apk（本轮手机为 RUNNING_UNLOCKED）。
- 文字模型和视觉文件已复制到应用私有目录并验证完整 SHA-256，权限调整为0600。仅复制公共模型，没有迁移旧用户资料。
- 独立UID为10023；Android Keystore初始化返回 hardware=true。工具安全测试已返回SAFETY_COMPLETE；完整密钥绑定、拒绝错误密钥和重开测试尚未完成，因此不是“安全验收通过”。

## 测试停滞定位

初轮instrumentation停滞不是已证实的代码死锁。OPPO日志显示 OplusHansManager 将应用UID10023按 StrictMode-1 / LcdOff 冻结，阻止计时器、测试线程和调试器继续执行。没有关闭系统省电、安全验证或锁屏保护。

debug-only测试页已加入FLAG_KEEP_SCREEN_ON和FLAG_SECURE；用户解锁并显示自检页后，可避免正常熄屏打断。页面只显示合成测试状态，测试结束关闭。调试版还增加分阶段进度和线程等待诊断，不显示密钥、口令或私人内容。

## 下一步验收

1. 亮屏解锁后完成 security instrumentation，记录 APK_SAFETY_OK。
2. mode=model instrumentation 在应用UID中启动LocalService，验证文字、视觉、实例HTTP密钥门禁和正式资料库未初始化。
3. 验证模型子进程退出，覆盖安装非debug版本；确认run-as拒绝、模型保留和正式启动。
4. 真实WebView选图、锁定/切后台/文件选择器60秒例外仍需要操作验收。

本记录不能替代真机测试结果。构建脚本现自动生成每个APK的大小、SHA-256、版本及debug标志，并校验签名、ZIP完整性和对齐；设备验收状态单独记录，避免重建后沿用旧包哈希。
