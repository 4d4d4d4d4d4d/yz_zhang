# 小千 Android 工程（0.5.19）

独立APK，包名org.qwen.local，versionCode 24。当前处于真机开发验证阶段；以[最新交接](../docs/HANDOFF.md)为准，不代表商业发行验收通过。

## 构建依赖

构建入口为 `build-apk.py`，没有Gradle工程。当前脚本依赖以下本地文件（均不上传）：

- JDK：通过 `QWEN_JAVA_BIN` 指定bin目录；默认仍为开发机PyCharm自带JBR路径。
- `tools/sdk-build/android-15/`：Android build-tools 35.0.0，aapt2、zipalign、apksigner及其lib目录。
- `tools/sdk-platform/android-35/android.jar`：Android API 35。
- `tools/r8.jar`：D8；旧shell构建和部分测试另需tools/android.jar及tools/json.jar。
- `tools/zig/ziglang/zig`：Zig 0.14.1，用于ARM64生命周期预加载库。
- `build/runtime/android-cpu/llama-b11527/`：Android ARM64 llama-server及动态CPU变体、libllama-server-impl.so、libllama-common.so、libmtmd.so、libllama.so、libggml.so和libggml-base.so。
- `build/runtime/llama-b11527/LICENSE`：运行时许可证，构建时打包进APK。

这是已有开发环境的构建流程；从零下载并构建上述依赖尚未自动化。运行时与模型元数据见根目录manifest.json，第三方代码和二进制需遵守各自许可。

```sh
export QWEN_JAVA_BIN=/path/to/jdk/bin
python3 build-apk.py
# 仅供本机调试，允许投屏且关闭后台/空闲自动锁库
python3 build-apk.py --screen-debug --keep-vault-unlocked
```

普通包输出build/qwen-local-beta.apk；投屏调试包输出build/qwen-local-screen-debug.apk。构建验证签名、ZIP完整性和16KiB对齐，并生成元数据JSON。tools/signing/中的签名私钥和随机密码只保存在本机，不要提交；丢失签名材料会影响覆盖更新。

## 安装和运行

要求ARM64，minSdk28、targetSdk35；截屏需Android11+。目前主要在OPPO PGEM10/SM8550 Android16验证，不承诺所有机型兼容。

```sh
export QWEN_PHONE_SERIAL=your_authorized_device_serial
./tools/platform-tools/adb -s "$QWEN_PHONE_SERIAL" install -r build/qwen-local-beta.apk
```

模型不打包进APK。应用内分别导入固定版本的Qwen3.5-4B Q4_0及F16视觉投影器；大小和哈希在MainActivity中校验。已导入模型时打开应用启动可见前台服务；通知和应用按钮可停止。

原生“应用查询”目前仅在keep-vault-unlocked调试构建启用，需已解锁资料库、开启无障碍服务，并选择具体应用范围。只支持有限查询导航；不是通用自动操作授权。详细限制见主README和交接文档。

## 数据保护

独立UID、私有目录、AES-GCM记录、口令派生并绑定Android Keystore；默认禁用备份，启用FLAG_SECURE和后台/空闲锁库。硬件安全等级、备份恢复和独立安全审查未完成。

WebView仅允许本应用loopback页面，不公开通用JS原生桥。当前需要网络、前台服务、通知及用户手动开启的Accessibility能力；没有已验收的原生麦克风唤醒或微信发送能力。

`--debug`包含隔离测试Instrumentation，仅在专用测试安装使用，不应覆盖含个人资料的设备来做破坏性测试。宿主机单元测试见根README；历史设备记录见reports目录。
