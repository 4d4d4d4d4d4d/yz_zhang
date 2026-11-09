# SignalNet

以 **Proof of Signal（声誉质押）** 衡量信息可靠性与质量的去中心化内容社区：
好内容靠质量被看见，而不是靠投流；读者看广告，创作者和帮助发现好内容的策展人获得收益。

- 愿景：[docs/VISION.md](docs/VISION.md)
- 规格：[docs/SPEC.md](docs/SPEC.md)
- 架构：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 路线图：[docs/ROADMAP.md](docs/ROADMAP.md)
- 贡献协议（先读）：[AGENTS.md](AGENTS.md)

## 快速开始

```bash
cd signalnet
pip install -r requirements-dev.txt
make demo       # 端到端仿真：诚实评审 vs 合谋刷分、广告分账、日志重放
make gate       # 入库门禁
make iterate    # 刷新 TODO.md，给出下一项任务
```

当前状态：M1 可验证内核（单进程库），29 条 P0 需求全部有测试追溯。
