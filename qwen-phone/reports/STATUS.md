2026-10-14 恢复记录：ADB 连接正常，但 18090/18180 转发缺失且 PhoneAgent/llama-server 进程不存在；已恢复转发并以日常 HTP 28 层配置重启，两个 health 均正常。退出原因尚无证据，不能确定为系统回收。UI 已微调为冷白、石墨灰、低饱和蓝并检查正式入口及无用户数据聊天预览。以下为历史记录。

# 端侧部署实测结果

更新时间：2026-10-11。当前服务：实验性 HTP staging 全层卸载（-ngl 99），CPU 5 线程，microbatch64，4096-token 上下文，关闭融合。日常默认仍为 28 层。

v2 已实现 reasoning 展示、工具任务轮询、三种 skill、真实 token 预算与本地上下文压缩、逐次批准网页搜索，以及加密画像/笔记/历史对话。详见 [NPU 诊断](NPU-DIAGNOSIS.md)、[隐私边界](PRIVACY.md)。

v2 短测 pp128/tg16/r2：28 层 127.25/9.99 token/s；30 层映射失败；GPU+NPU 为 78.41/9.56。实际 agent 完成设备/时间（22.61 秒）、加密笔记写读（24.69 秒）、reasoning 数学题（18.09 秒）、批准搜索（50.07 秒）、拒绝搜索（19.40 秒）、压缩后历史回忆（21.93 秒）。这些时间是测试请求样本，不是通用延迟保证。

以下表格保留 v1 的 pp128/tg32 对照，不与不同 decode 长度的 v2 数据作严格比较。

## 已完成

- OPPO PGEM10 / SM8550 / Android 16，约 16 GB RAM。ADB 已授权。
- Qwen3.5-4B Q4_0 权重已在 Mac 与手机分别通过 SHA-256 校验。文本模型已部署，未部署视觉编码器。
- llama.cpp b11527 与 Java/Dex agent 均在手机执行，无云端模型调用。
- 模型真实调用 device_status、get_time，返回设备和时间；用时 18.406 秒。
- 模型真实调用 write_note、read_note，写入并读回 qwen35-agent-ok；用时 9.703 秒。
- 路径限制、工具白名单、同源请求限制和推理 API 认证已验证。

## 短时性能

固定同一份 Q4_0 权重；128-token prefill、32-token decode、每项重复 2 次。CPU mask 为 f8。单位：token/s。

| 配置 | 输入处理 | 生成 |
| --- | ---: | ---: |
| CPU 4 线程（单核绑定） | 40.66 | 8.25 |
| CPU 5 线程（大核集合内调度） | 43.24 | 11.10 |
| CPU 4 线程 + NPU 16 层 | 66.41 | 8.22 |
| CPU 4 线程 + NPU 24 层 | 102.16 | 9.02 |
| CPU 5 线程 + NPU 24 层（v1 默认） | 103.97 | 9.68 |
| 同上，关闭 NPU 算子融合 | 101.23 | 9.47 |

v1 异构配置的输入处理约为优化后 CPU 的 2.40 倍；生成速度约慢 13%。选择异构作为 agent 默认配置，是因为工具定义与多轮上下文需要较多输入处理；纯 CPU 模式仍可切换。测试规模较小，未测长时间热稳态与能耗，不能据此宣称达到硬件极限。

## 算子与边界

- NPU 实际 profiling 记录了 HMX tiled MUL_MAT、融合 MUL_MAT_NX、RMS_NORM+MUL、SSM_CONV、HMX chunked GATED_DELTA_NET+CPY。日志为 htp-profile.log，汇总为 htp-profile-summary.json。
- CPU 使用上游 ARM NEON/dotprod/i8mm 优化构建；未新增自定义汇编内核。NPU 使用上游 HVX/HMX、DMA/VTCM 与融合算子。
- 关闭算子融合后的短测略慢（101.23/9.47 对比 103.97/9.68）；差异较小，不作统计显著性结论。
- 原版全量与 32 层 NPU 卸载失败，原因是 FastRPC buffer mapping；缩小内存块与 VMEM 后全量仍失败。v2 进一步验证了 28 层，30 层仍失败；详见专项诊断。
- 单核心强制亲和性在 HTP 初始化后有 EINVAL 警告；改为在大核集合内调度后消失。
- 当前是 CPU/NPU 分层执行。尚未用时间线证明两者计算重叠，不称为已实现真正的异构并行。
- 当前为开发部署，不是前台服务 APK；重启或系统回收后需从 Mac 重新启动。v2 支持加密多轮会话、六种受限工具及三种 skill，不支持任意跨应用控制。

## 使用

- 手机浏览器：http://127.0.0.1:8090/
- Mac 浏览器（ADB 连接时）：http://127.0.0.1:18090/
- 重新启动：`python phone.py start`
- 纯 CPU：`python phone.py start --backend cpu --threads 5`
- 停止：`python phone.py stop`

具体依赖版本和文件哈希见 ../manifest.json；服务操作见 ../README.md。

## v2 最终验证

- 正式服务已启动，health 返回 version=2、test_vault=false；正式用户口令未预设。
- 3151-token 输入通过，返回“测试完成”，输入处理约 109.31 token/s；未触发 NPU 映射错误。此处只生成 4 token，不用它估计稳态 decode 性能。
- 浏览器实测保存画像、模型 reasoning 展开与历史会话列表；页面已回到正式资料库创建入口。
- 加密自测包含重开、错误口令、已解锁状态重新认证、密文篡改和已知明文扫描。
- 认证测试包含旧 token 撤销、错误重新认证后原会话仍可用、会话索引恢复/删除，以及锁定取消进行中的任务。
- 工具组合测试先查询时间，再调用 compress_context，仍正确返回历史测试代号 ORBIT-73 和当前工具时间。
- 隔离测试数据库已清理，未初始化正式用户资料。

## NPU staging 实验验证

固定 RPCMEM 池已绕过当前全层卸载映射失败，pp128/tg16/r2 为 124.71/2.85 token/s；生成速度明显低于 28 层模式。真实推理通过字符串、乘法、2432-token 回忆和连续新请求测试。仅使用公开合成提示，没有解锁或初始化正式用户资料库。实现锁定 b11527 ABI，未修复驱动根因、未完成长时压力测试；详见 NPU-DIAGNOSIS.md 和 ../native/README.md。
