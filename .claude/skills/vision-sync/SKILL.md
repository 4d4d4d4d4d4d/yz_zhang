---
name: vision-sync
description: When the user states a new requirement, pain point or direction, record it verbatim in docs/VISION.md, expand it into user segments and pain points, add comparison rows, and turn it into ordered items in docs/BACKLOG.md — without asking the user. Use before starting implementation of any newly stated need.
---

# 把用户新说的话变成愿景与待办

1. **原话入档**：`docs/VISION.md` 第 1 节新增一小节「1.x 主题（日期）」，**逐字引用**用户原话（引用块），下面写「落到工程上的是…」。
2. **人群与痛点**：如果涉及具体人群，更新 1.7 那张表（人群 / 痛点 / AI 要做的 / 批次）。
3. **对照行**：第 2 节加 `V-NN` 行；状态只能是 `两端已接 / 仅 web / 仅后端 / 未实现 / 部分`（`test_vision_checklist.py` 核对）。
4. **待办**：`docs/BACKLOG.md` 按优先级插入批次（编号、标题、spec、状态 `todo`），写一句「为什么排在这里」。
5. **业界**：需要时查资料（WebSearch），把做法和链接写进将来那一批的 spec。
6. `python -m scripts.harness check` 全绿后与那一批的代码一起提交。
