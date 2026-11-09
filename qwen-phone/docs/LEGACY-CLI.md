> 历史shell服务说明，保留当时配置与实验数据；不代表当前APK状态。最新状态见 [HANDOFF.md](HANDOFF.md)。

# Qwen3.5-4B 手机本地助手 v2

OPPO PGEM10 / SM8550 / Android 16 / 约 16 GB RAM；llama.cpp b11527；Qwen3.5-4B Q4_0 文本权重。版本与哈希见 `manifest.json`。不含视觉编码器。

## 使用

在本目录执行，Python 3.11+（当前机器 `/opt/miniconda3/bin/python`）：

```sh
sh probe-device.sh
sh build-agent.sh
python phone.py start
python phone.py status
```

Mac 打开 <http://127.0.0.1:18090/>；手机浏览器打开 <http://127.0.0.1:8090/>。首次使用自行创建至少 12 字符的资料库口令。没有预设口令，也没有找回后门。

- 日常助手：时间、设备、加密笔记、联网检索、上下文压缩。
- 离线助手：服务端禁用搜索工具。
- 网页研究：搜索结果附链接；每次联网先确认将发送的查询。目前只读取搜索摘要，不是完整网页抓取。
- 勾选“显示模型 reasoning”查看 Qwen 实际返回的 `reasoning_content`。每轮完成后展示，非逐 token 流式显示，也不代表可信的内部因果解释。工具阶段以轮询方式更新。
- 对话自动加密保存，可以切换或删除历史会话；输入接近预算时在手机上压缩已完成历史，并保留近期消息。也可手动勾选压缩。先用实际聊天模板和 tokenizer 校验 4096-token 预算；超限且无法安全压缩时返回明确错误，不静默截断。
- 画像支持手动资料、本会话任务和已确认回答偏好。勾选收集后，仅从本次明确表达识别四类回答风格，生成待确认候选；候选不参与回答，30 天到期。删除一行画像后保存即可移除。详见 [MEMORY.md](../reports/MEMORY.md)。
- 锁定会撤销认证、取消任务并清除待执行队列；15 分钟无 API 操作自动锁定。

```sh
# CLI 会交互询问口令，联网另行显示查询并询问；结束时锁定
python phone.py ask --prompt '请查询这台手机的型号和当前时间。'
python phone.py ask --thinking --skill offline --prompt '计算 17 乘以 23。'
# CPU 路径；重新启动会要求再次解锁
python phone.py start --backend cpu --threads 5
python phone.py logs
python phone.py stop
```

## 端侧架构与调度

手机浏览器/ADB 转发 → 手机 Java/Dex `PhoneAgent` → 手机 `llama-server` → Qwen → 手机工具。Mac 仅做部署、测试与转发，无云端模型推理。网页检索是用户批准后的外部网络访问。

默认 CPU 5 线程、mask f8、strict=0，HTP0 卸载 28 层，batch256 / microbatch64，context4096，一个推理 slot。CPU 使用 upstream NEON/dotprod/i8mm 内核；NPU 使用 HVX/HMX 与算子融合。独立的时间与设备只读工具并发，模型请求有界排队，笔记读写保留依赖顺序。没有宣称实现 CPU/NPU 同一 token 的完全并发。

新短测 28 层 pp128 / tg16：127.25 / 9.99 token/s；原版 30 层及全卸载遇到 FastRPC 映射失败；新增固定 staging 池已实验性跑通全层卸载，短测 124.71 / 2.85 token/s，拷贝开销使生成更慢。GPU+NPU 测试较慢。默认配置是当前实测可用选择，不代表硬件绝对极限。详见 [NPU-DIAGNOSIS.md](../reports/NPU-DIAGNOSIS.md)、[STATUS.md](../reports/STATUS.md)。

## 数据保护与限制

SQLite 记录用 AES-256-GCM 加密；口令通过 PBKDF2-HMAC-SHA256（600,000 次）派生密钥；记录标识用 HMAC。正式库位于手机 `private/vault.db`，测试库隔离。未持久化口令或明文主密钥，浏览器不用 localStorage 保存私密内容。

当前是共享 ADB shell UID 的开发服务，尚未封装独立 APK/前台服务、接入硬件 Keystore；重启手机需重新启动，也可能被系统回收。加密不能防御解锁时的恶意同 UID 进程或被控制的宿主机。详情见 [PRIVACY.md](../reports/PRIVACY.md)。旧 v1 明文演示笔记不会自动迁移或删除，v2 使用新加密笔记存储。

每任务最多 5 轮推理、8 次工具调用；联网确认最多等待 3 分钟。不会执行任意 shell、点击其他应用、发短信或付款。搜索命中率和小模型回答质量仍需改进；不要将 reasoning 文本或搜索摘要视为事实验证。

## 构建与验证

`build-agent.sh` 编译所有 Java 文件并使用 D8 打包；依赖现有 JDK、`tools/android.jar`、`tools/json.jar`、`tools/r8.jar`。不把这些二进制依赖、模型、密钥提交到 Git。

```sh
# 真机加密自测，仅操作 isolated.db
./tools/platform-tools/adb -s "$QWEN_PHONE_SERIAL" shell \
  'CLASSPATH=/data/local/tmp/qwen-phone/agent.jar app_process /system/bin PhoneAgent --self-test'
# 性能测试会停止模型服务，完成后需重新 start
python phone.py bench --backend htp --threads 5 --layers 28 --label htp28
```

`tests/integration.py` 验证认证/同源、工具、加密笔记、reasoning、搜索允许/拒绝、压缩回忆、画像删除和锁定/重开。只允许在使用 `PhoneAgent --test-vault` 启动的空白隔离库运行；不会初始化正式用户库。

参考：[Qwen 官方模型](https://huggingface.co/Qwen/Qwen3.5-4B)、[量化权重](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF)、[llama.cpp Snapdragon 后端](https://github.com/ggml-org/llama.cpp/tree/b11527/docs/backend/snapdragon)。

## NPU 全层卸载实验模式

当前真机已运行该模式；日常默认仍为 28 层。固定缓冲池规避了目前复现的映射失败，尚未修复厂商驱动根因。详见 [实现与限制](../native/README.md)。

```sh
sh build-native.sh
python phone.py start --backend htp-staging
python tests/staging-inference.py
# 恢复日常较快配置
python phone.py start --backend htp
```

启动与切换会重启服务，需要重新解锁资料库。实验模式强制全层卸载并关闭融合，启动前校验运行库版本；不能与多设备或其他模型直接混用。

## 界面与语音

新版小千界面提供前台“小千”唤醒、听写草稿和本地声音朗读。取决于访问页面的浏览器、中文语言包与麦克风权限；不支持时禁用，不回退云端。不是熄屏常驻唤醒。当前内置浏览器需下载中文语音包，真实音频链路待验证。详见 [VOICE-UI.md](../reports/VOICE-UI.md)。

## Android 内测候选

新增独立 APK 构建与设备密钥绑定，见 [android/README.md](../android/README.md)。发布候选不是商业上线验收通过：原生真机安装目前等待手机解锁，验收状态见 [BETA-ACCEPTANCE.md](../reports/BETA-ACCEPTANCE.md)。网页端新增笔记确认、取消任务与最近 100 轮聊天回显。
