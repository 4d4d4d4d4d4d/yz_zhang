# 固定 RPCMEM staging 池（实验）

目标是规避当前 SM8550 / Android 16 上 b11527 全层卸载的 FastRPC 映射失败。不是厂商驱动修复，也不是可移植的后端补丁。当前服务使用此模式；日常启动默认仍为较快的 28 层配置。

## 构建与复现

从 qwen-phone 目录执行。依赖已部署的模型、ADB 和 llama-b11527，以及隔离的 Zig 0.14.1 工具链。当前 macOS arm64 主机工具链来自 PyPI 的 ziglang 0.14.1 wheel，解压后可执行文件位于 tools/zig/ziglang/zig。可在新环境用 `python -m pip install --no-deps --target tools/zig ziglang==0.14.1` 安装对应平台工具链。

```sh
sh build-native.sh
python phone.py start --backend htp-staging
python phone.py status
python tests/staging-inference.py
# 通用性能命令使用 pp128/tg32/r2，与报告的 tg16 不同
python phone.py bench --backend htp-staging --label staging --repetitions 2
# bench 会停止推理服务，完成后重新启动
python phone.py start --backend htp-staging
# 回退日常配置
python phone.py start --backend htp
```

构建脚本仅编译 map-staging.c，并通过临时文件替换手机的 shim。phone.py 在停止旧服务前校验 runtime-lock.json 中两份运行库的哈希及本机/手机 shim 一致性。只给本次推理进程设置 LD_PRELOAD，不修改系统库。更换 upstream 版本必须重新审核 ABI 和实现，不能简单修改锁文件使检查通过。

## 工作方式与约束

- 拦截 enqueue_op，复用四个 128 MiB 权重槽和一个最大 576 MiB 权重槽。总池上限 1088 MiB，不包含原权重、KV、计算和队列。
- 拷贝前等待在途操作完成，对 DMA buffer 执行写入前后缓存同步。原 enqueue 捕获描述符后恢复原权重指针。
- 强制 OPFUSION=0，避免融合路径重新访问恢复后的指针。MBUF=64,128，VMEM=1536，单 HTP0、单推理 slot、context4096、microbatch64。
- 仅验证当前 Qwen3.5-4B Q4_0 不可变权重。依赖固定 Android arm64/libc++ 对象布局，静态偏移检查无法替代运行库哈希校验。
- 池资源随进程退出回收；没有实现通用设备重建和跨 session 生命周期。多 session、动态权重、其他模型、更大权重块和融合均不在支持范围。
- 复制和同步开销显著降低 decode 速度。已通过短 bench 和有限真实提示测试，未完成长时热稳态、全算子精度对照或并发压力测试。

后续可将该逻辑移入 upstream 源码，使用正式结构和 RAII 生命周期，逐步减少权重重复复制，再评估安全的融合与预取。当前不能据此宣称 CPU/NPU 已实现同一 token 的计算重叠。

失败原型位于 experiments/，仅作诊断记录，不参与构建。故障证据和性能见 [NPU-DIAGNOSIS.md](../reports/NPU-DIAGNOSIS.md)。
