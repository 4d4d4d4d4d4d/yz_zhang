# 27B 多模态候选准备 · 2026-10-18

目标：评估比当前4B更大的手机本地视觉模型。候选为Qwen3.5-27B，不能声称其IQ2量化版是所有20B级模型中最强。

- 官方模型：https://huggingface.co/Qwen/Qwen3.5-27B
- 量化发布：https://huggingface.co/unsloth/Qwen3.5-27B-GGUF
- 固定revision：3221f178a6b842d04f1fb42f1c413534adcc0a6a
- 权重：UD-IQ2_XXS，8573593504字节；SHA256见model-27b-candidates.json。
- 视觉：F16，927607040字节；SHA256见同一清单。禁止复用4B的projector。
- 合计约9.50GB（8.85GiB），尚不含运行缓冲、上下文和系统内存。
- Q4_K_M权重为16740812704字节，超过此手机可见总内存，未下载。

手机上次可见内存约14.8GiB，可用约4.2GiB（含运行中的4B服务）。候选IQ2仍可能内存不足或因文件换页极慢；量化后准确率也需要实测。当前Hexagon后端的量化重排类型列表没有IQ2_XXS，因此首次评估应采用CPU，不应承诺NPU加速。

## 可复现工具

下载：download-candidate.py，固定revision、分块断点续传、完整SHA256校验后才生成最终文件。

准备：candidate-27b.py verify / preflight / deploy。deploy先校验全部文件，并依据当前MemAvailable与权重+2GiB估计做保守内存门槛；通过后才复制到candidate-27b独立目录，手机端再次校验。该门槛不代表精确峰值预测。工具不覆盖4B、不改APK、不宣称已经加载27B。

ADB标准5037端口发生占用；备用5038服务可启动，但当前未发现手机，macOS USB列表亦未识别到手机。phone.py新增QWEN_ADB_PORT配置，默认保持5037；必要时使用QWEN_ADB_PORT=5038运行候选准备工具。

## 后续验收

连接恢复后先测可用内存，必要时在可回退的测试窗口暂停4B，再决定是否允许加载27B。加载成功后分别测试短文字、同一模拟订票截图，并记录峰值内存、首字延迟、总耗时、按钮状态判断。未验证通过前保留4B默认，不放宽APK模型哈希校验。

## 本轮交付状态（17:47）

两份最终文件均已完整下载，下载器SHA256校验通过；candidate-27b.py verify再次验证准备工具可正确读取并校验，结果保存model-27b-verified.json。合计9501200544字节。ADB 5038最后复查仍为空列表。没有传入手机、没有加载27B、没有修改已安装APK，4B模型文件保留。

## 实机实验结果（连接恢复后）

ADB标准5037已恢复，设备[device serial omitted]。两文件均传到手机candidate-27b独立目录，并在手机上通过SHA256校验。

当前可用内存未满足保守门槛；作为单次诊断，使用独立tests/27b-device-trial.py进行明确标记的低内存实验，不改变默认部署门槛。CPU 4线程、2048上下文、batch64/ubatch32、图像上限1024token，进程360秒总限时，内存可用小于256MiB即终止。

- 含视觉模块加载成功，health就绪16.1秒。
- 文字“只回答2+3的数字结果”：正确返回5，耗时32.18秒。
- 后端文字日志：22输入token预处理30.24秒，约0.73token/s；生成统计约0.53token/s。单次短样例不是稳定吞吐基准。
- 同一模拟订票JPEG截图：180秒请求超时，没有得到视觉回答，不能评价视觉准确率，也不能称视觉验收通过。
- 观察到进程VmHWM 9058460KiB（约8.64GiB）；曾出现约0.68GiB VmSwap。加载成功不等于无内存压力，未证明超时完全由换页造成。
- 本实验CPU IQ2不能与4B HTP的耗时直接解释为纯模型规模差异。
- 候选进程已发出停止信号，默认模型仍为4B；正在恢复4B HTP28视觉服务。没有更新APK或改其模型校验。

原始数据：model-27b-trial.json、model-27b-trial.log、model-27b-process-memory.txt。结论：27B IQ2在此手机上可以加载，但本轮不满足交互可用性，不能宣称已完成默认模型升级。

恢复确认：候选在SIGTERM后仍未退出，核对PID命令行确为candidate-27b/model.gguf后执行SIGKILL，候选进程释放内存；脚本补充同样的退出兜底。已移除18186实验转发。4B HTP28服务恢复，health=ok、vision=true、vault_initialized=false。
