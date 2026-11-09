# 贡献指南

完整工作协议见 [AGENTS.md](AGENTS.md)。这里是速查版。

## 环境

```bash
cd signalnet
pip install -r requirements-dev.txt
make hooks      # 安装 pre-commit：提交 signalnet/ 改动时自动跑门禁
```

## 流程

1. `make iterate` 看下一项任务
2. 先改 `docs/SPEC.md`（新需求设为 P0 并写验收标准）
3. 先写测试（docstring 标注 `REQ-XX-000`），再写实现
4. `make gate` 全部 PASS
5. 提交信息：`<type>(<REQ-ID>): <说明>`，type ∈ feat / fix / refactor / docs / test / harness

## 评审清单（PR 自检）

- [ ] 没有破坏 SPEC §4 的五条不变量
- [ ] 新模块已在 `harness/gate.py::LAYERS` 登记
- [ ] 新事件类型已在 `SignalNode.replay` 支持
- [ ] 没有删除、跳过或弱化测试
- [ ] 文档（SPEC / ARCHITECTURE / ROADMAP）已同步
