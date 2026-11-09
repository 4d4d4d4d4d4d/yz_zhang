# 仓库说明

- `file_organizer.py`：早期的独立文件整理工具。
- `signalnet/`：SignalNet 去中心化内容社区项目。**在 `signalnet/` 下工作前，先读 `signalnet/AGENTS.md`**，并在提交前运行 `cd signalnet && make gate`。

## 工作偏好

- 迭代时不要每轮询问是否继续，按 `signalnet/TODO.md` 与 `signalnet/docs/ROADMAP.md` 的顺序自动接着做；只有需要所有者拍板的设计取舍才提问。
- 可以先批量实现 SPEC 功能，再统一测试、修 bug、修订 SPEC（详见 `signalnet/AGENTS.md` §4）。
