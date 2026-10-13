# 工程 harness：怎么在这个仓库里迭代

> 这一页给在这个仓库里写代码的人（以及 AI 助手）。规则来自用户 2026-10-13 的要求：
> 「在工程里建立一些基本的 harness skill 和 spec 文档库……合入代码实现能够跟 spec 对应……
> 不需要我来提醒，最好能够通过 harness 和 skill 自动做 spec 和文档的迭代……不要一直询问我。」
> 目标是**商业化交付**，愿景在 [`docs/VISION.md`](docs/VISION.md)，商用差距在 [`docs/STATUS-2026-10-13.md`](docs/STATUS-2026-10-13.md)。

## 1. 去哪里找

| 东西 | 位置 |
|---|---|
| 愿景原话与逐条对照（闸门核对） | `docs/VISION.md` |
| 活的待办（下一批做什么） | `docs/BACKLOG.md` |
| spec 文档库与索引 | `docs/specs/`，`docs/specs/README.md` |
| 现状台账（已做 / 欠 / 外 / 有意不做） | `docs/specs/72-status-ledger.md` |
| 功能面清单（只增不减） | `docs/FEATURE-SURFACE.txt` |
| 批次做法（skills） | `.claude/skills/*/SKILL.md` |
| 脚手架与检查 | `server/scripts/harness.py`（`new-spec` / `check` / `backlog`） |
| 全量回归（独立 worktree） | `tools/regress.sh` |

## 2. 一批怎么做（详见 skill `spec-batch`）

1. **取活**：从 `docs/BACKLOG.md` 取最上面的一批；用户新说了需求，先走 skill `vision-sync` 写进愿景与待办；待办不多了，走 skill `scenario-discovery` 按方法发掘新场景（不只做用户举过的例子）。
2. **写 spec**：`python -m scripts.harness new-spec "标题" --batch V147 --ids KB-100~110`，生成带编号的 spec 骨架并登记进索引。写清：来源原话、业界做法、数据、接口、两端、隐私与边界、闸门与红验、没做的。
3. **实现**：服务端、共享 SDK（`packages/core`）、Web、App 一起做；**功能只增不减**——不删接口、页面、SDK 方法，替换要进 `RETIRED` 并写理由（FEAT-001）。
4. **测试**：每条闸门都要**红验**（故意改坏一处，对应测试必须变红，再改回）。
5. **登记**：新错误码进 `packages/core/src/i18n.ts`；新接口进功能面清单（`python -m scripts.feature_surface --write`）；带资源 id 的接口进对象级授权表；新表进迁移；新 job 进调度表；新字段进注销处置表与数据导出。
6. **文档**：spec 状态、台账、愿景对照、完成度文档、计数（以测试输出为准）、版本号。`python -m scripts.harness check` 全绿。
7. **回归**：`tools/regress.sh` 在独立 worktree 里跑全量：后端、三端、lint、类型检查、计数核对、真浏览器联调。**全绿才推送**。
8. **提交**：一批一个提交，提交说明写批次号与 spec 号。只推送到指定的开发分支。

## 3. 不变的规则

- 不问用户：愿景和商业化目标已定，按 BACKLOG 一直往下做；真正需要外部资源的（持牌机构、真机、外部账号）记作「外」，不阻塞别的。
- 只增不减：兼容原有实现；改旧行为要说明，旧测试的断言只能扩展、不能为了通过而删。
- 密钥只从环境变量读取，不入库、不写日志。
- 钱、签署、申报、对外发布：AI 只出草稿，人确认。
- 文案用人话：错误信息说清「为什么」和「怎么办」。
