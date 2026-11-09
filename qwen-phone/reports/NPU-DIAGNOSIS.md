# SM8550 NPU 内存映射诊断与并行策略

2026-10-11；OPPO PGEM10 / Android 16；llama.cpp b11527（ba6439a6b）；Qwen3.5-4B Q4_0。本文记录真机现象；未修改系统或厂商驱动，新增了进程内的实验性固定映射缓冲池绕过方案。

## 失败位置与证据

全卸载失败发生在 `fastrpc_mmap`，不是 Java 堆分配或模型文件读取：`domain_id 3`，错误码 `0x00000001`。`reports/v2/full-debug.log` 的同一批次已记录以下映射：

| 缓冲区 | 字节 |
| --- | ---: |
| 计算 | 132,460,544 |
| 权重块 1 | 1,064,030,208 |
| recurrent state | 52,695,040 |
| KV | 8,392,704 |
| 权重块 2 | 1,069,461,504 |
| 批次累计 | 2,327,040,000 |
| 下一权重块，映射失败 | 489,271,296 |

此外还有队列与 fence 的约 10.97 MB 映射，未计入该批次计数。因此不能把 2.327 GB 当作精确的驱动硬上限。日志支持“FastRPC/DSP 映射资源或地址空间边界”，不能仅凭错误码确定驱动内部的具体限制、碎片情况或精确最大值。设备仍有数 GB 可用物理内存，物理 RAM 不足不是现有证据支持的解释。

`GGML_HEXAGON_VMEM=0` 探测返回 1,879,048,192 字节（1.75 GiB）。源码探测按大块分配、失败后回退一个 256 MiB 步长；这是保守探测值，不是硬件规格。降低 VMEM、使用较小 MBUF 和 microbatch 后，全卸载仍失败。对应日志：`reports/v2/full-vmem-probe.log`。

## 源码对应

文件 `vendor/llama-b11527/ggml/src/ggml-hexagon/ggml-hexagon.cpp`：

- v73 默认 `opt_vmem` 为 3000 MiB；实测旧 FastRPC 路径不能据此保证同等大小的可用映射窗口。
- `mmap_tensor()` 约 4676 行：已映射 buffer 会保留 host 映射；当前 v73 路径未启用 DMA64 extended mapping。
- `enqueue_op()` 约 4387 行：先 `mmap_tensor()`，再 `fit_op()` 和批次 flush。因此仅缩小 batch 的 VMEM 预算，不等于释放先前建立的所有 host/FastRPC 映射。
- `ggml_hexagon_measure_max_vmem()` 约 4747 行：上述探测算法。

上述代码使映射保留成为一个候选原因，但进一步实验不能支持它是唯一原因：同步完成每个算子、执行 HTP unmap 和 FastRPC munmap 后，显式存活映射约 77.9 MB 时，新的约 556 MB 映射仍失败。提前映射最大块可以成功，但后续约 131 MB 映射在显式存活约 634 MB 时失败，底层日志出现 errno=14（EFAULT）。重新注册 buffer 也未解决。因此不能把失败直接归因于单一 2 GB 上限或普通 RAM 不足。

驱动内部 DMA/SMMU 映射保留或碎片化仍是候选原因；目前没有对应内核证据，不能确定根因。Qualcomm 开源 FastRPC 的映射包装会把多种底层错误转成通用错误 1，单看该返回码不足以定位原因。参考 [Qualcomm FastRPC](https://github.com/quic/fastrpc)。

## 已部署的实验性绕过

`native/map-staging.c` 为精确锁定的 b11527 Android arm64 二进制增加进程内 LD_PRELOAD shim。它复用四个 128 MiB 小槽和一个最大 576 MiB 大槽，将不可变权重拷入固定 RPCMEM 缓冲池，而不是不断给新的权重分配建立 DSP 映射。池上限 1088 MiB，另外仍有原权重、计算缓冲区、KV/state 和队列，因此这不是总内存上限，也不是零拷贝。

覆盖槽位前同步等待在途 DSP 工作，拷贝前后执行 DMA buffer cache sync；原 enqueue 捕获描述符后恢复 CPU 侧指针。必须关闭算子融合，以避免后续融合重新读取已恢复的指针。仅支持一个 HTP0、一个推理 slot、当前不可变权重模型；启动前校验两份 upstream 库及 shim 的 SHA-256。不适用于任意版本、并发多设备、动态修改权重或开启融合。

全层卸载配置 `-ngl 99` 已跑通 pp128/tg16/r2，并连续通过固定字符串、乘法、2432-token 上下文回忆和新请求验证；没有再次出现映射错误。不支持的算子仍可能在 CPU 执行，不能称为所有计算都在 NPU。该结果是实验性规避，不是驱动根因修复；尚未完成长时间压力测试或系统性数值精度评估。

构建、切换和约束见 [native/README.md](../native/README.md)。原始日志在本地 `reports/npu-fix/`，包括失败的 window/early-map 实验、`staging-batch.log/json` 以及 `staging-inference.json`。失败原型保存在 `native/experiments/`，不由正常构建脚本部署。

## 实测选择

同一模型、CPU mask f8、5 线程、strict=0，pp128 / tg16，重复 2 次，batch256 / microbatch64：

| 配置 | 输入 token/s | 生成 token/s | 结果 |
| --- | ---: | ---: | --- |
| NPU 28 层 + CPU | 127.25 | 9.99 | 通过 |
| NPU 全层卸载，固定 staging 池，关闭融合 | 124.71 | 2.85 | 通过，实验模式 |
| 原版 NPU 30 层 + CPU | — | — | FastRPC 映射失败 |
| GPUOpenCL/HTP0，tensor split 1/3，全层分配 | 78.41 | 9.56 | 可运行，较慢 |

日常默认仍为 NPU 28 层、CPU 5 线程、microbatch64、4096 context、一个推理 slot。该 28 层配置已在实际 agent 的多轮工具请求、reasoning、搜索与压缩任务中验证，不只使用短 bench。最终在正式 4096 context 配置下，3151-token 输入也通过，输入处理约 109.31 token/s。staging 的拷贝和同步开销使生成显著变慢，不能视为性能优化完成。当前设备为便于继续诊断运行 staging 模式，普通 `start` 仍选择 28 层。表格来自短测，未控制所有热状态，未完成长时能耗/热稳态测试，不能称为绝对性能极限。

## 并行的实际边界

- CPU 使用现有 ARM NEON/dotprod/i8mm 优化内核，NPU 使用 upstream HMX/HVX 算子和融合；没有声称手写了新汇编算子。
- CPU 与一个 HTP device 的分层卸载不意味着两者对同一个串行 token 的所有层同时计算。
- `src/llama-context.cpp` 的流水线调度要求多 device、全层卸载以及每个非 CPU backend 都支持 async/events。GPU+NPU 测试没有出现 `pipeline parallelism enabled`，不能把其称作已实现真流水线并行。
- agent 采用有界 HTTP 线程池、单模型推理队列、3 个只读工具 worker；同一批的时间与设备信息读取可并发。笔记写入/读取按模型调用顺序执行，保留依赖。
- 同时加载 CPU 和 NPU 两套模型会增加 RAM/映射压力；未采用双实例推测解码。真正的 speculative decoding 需要另一个 draft 模型和正确性、接受率、内存、热状态验证，不应仅加线程就宣称实现。

官方实现说明：[llama.cpp Snapdragon backend](https://github.com/ggml-org/llama.cpp/blob/master/docs/backend/snapdragon/developer.md)。本报告的行为结论以本地 b11527 源码和真机日志为准。
