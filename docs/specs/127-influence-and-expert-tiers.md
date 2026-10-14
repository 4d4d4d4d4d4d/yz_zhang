
# 127 影响力与专家等级：不可转让、质押担保、罚没、衰减、Merkle 快照锚定

> 状态：本批实现（V152）。编号 INF-100~110。
> 来源：用户 2026-10-13：「也可以考虑用区块链 POS 来累计用户影响力从而提升专业能力成为专家。」VISION V-15；BACKLOG V152。
> 只增不减：撮合原有的四项加权、类目相关性加分、推断技能加分全部不变，只**多一项**类目等级小加分；
> 个人空间、个人中心只是**多一块**；纠纷、评价、完成的既有流程一行不改，影响力全部挂在事件总线上（`task.completed`、`dispute.resolved`）。

## 0. 要解决的问题

平台上「谁是这个类目的专家」现在只能看完成单数和平均星级：可以靠互刷单、刷好评堆出来，而且一次败诉之后毫无代价；
别人也没有办法用自己的信誉为新人作保——而这正是 PoS 的核心：**拿自己押着的东西为判断负责，判断错了要被罚没**。

## 1. 业界怎么做（带来源链接）

- **不可转让的身份信誉（Soulbound）**：Weyl、Ohlhaver、Buterin，《Decentralized Society: Finding Web3's Soul》（2022，<https://papers.ssrn.com/abstract=4105763>）——
  信誉必须绑在人身上、不能买卖转让，否则就变成了钱。这里：影响力账本只有「本人挣的 / 本人被罚的」，**没有任何转让、赠送、兑换、提现接口**（闸门钉住）。
- **质押与罚没（PoS slashing）**：以太坊 PoS 验证者押 ETH、作恶罚没（<https://ethereum.org/en/developers/docs/consensus-mechanisms/pos/rewards-and-penalties/>）。
  这里做成「担保」：熟手以上拿自己在该类目的影响力为别人作保，对方做成了担保人得 10%，对方败诉罚没担保额的一半。
- **信誉随时间衰减**：时间衰减的信誉模型（WWW 2013 时间衰减信誉相关工作；以及社区担保类项目的 vouch decay 做法）——旧成绩权重下降，专家要持续做成事。这里用 180 天半衰期。
- **评分通胀与互刷**：Filippas、Horton、Golden，《Reputation Inflation》（NBER w25857，<https://www.nber.org/papers/w25857>）——平台评分会持续向满分漂移。
  所以影响力**主要来自闭环成交**（按金额对数加权、封顶），评分只按偏离 3 星的幅度小幅加减；同一对人反复成交逐单递减（第 n 单记 1/n）。
- **Merkle 承诺与可验证快照**：Certificate Transparency（RFC 6962，<https://www.rfc-editor.org/rfc/rfc6962>）用 Merkle 树发布一批记录的根、任何人用路径证明某条记录在内。
  这里每日快照所有人各类目的影响力，树根写进平台存证哈希链（anchor_entries），每个人能取到自己那条的路径。

## 2. 数据

| 表 | 说明 |
|---|---|
| `influence_events` | 只增不改的账本：`earn_task` / `earn_publish` / `earn_vouch` / `slash_dispute` / `slash_vouch` / `restore`；`(user_id, kind, ref_type, ref_id)` 唯一——事件重放不重复记 |
| `influence_vouches` | 担保：担保人、被担保人、类目、可选的某一单、担保额、状态（担保中 / 已释放 / 已罚没 / 已撤回）、被哪次纠纷罚没 |
| `influence_snapshots` | 每日快照：Merkle 根、叶子数、存证序号、那一刻的叶子原值（证明用，不对外） |

迁移 `c1d220260018`（SQLite 与 Postgres 都验过 `alembic check`）。

**规则**（`app/modules/influence/service.py`）：

| 编号 | 规则 |
|---|---|
| INF-101 挣 | 完成一单：`10 × min(3, 1 + log10(1 + 预算/100 元))`；纠纷里拿到不足一半不挣，拿到一半以上按比例挣；与同一发单方 90 天内第 n 单只记 1/n；发单方得 0.2 倍；为这一单担保的人得担保额 10% |
| INF-102 读 | 有效影响力 = 账本各条按 180 天半衰期衰减之和 + **已揭晓**评价（每颗星偏离 3 星 ±2 点，同样衰减）；双盲揭晓前的评价不算——算进去就等于提前泄露星级 |
| INF-102 等级 | 新手 0；熟手 30 点 + 3 单；专家 120 点 + 10 单 + 实名 + 平均 ≥4.5 星 + 180 天内没有败诉；资深专家 300 点 + 30 单 + 实名 + ≥4.7 星 + 365 天内没有败诉；本人看得到「升到下一级还差什么」 |
| INF-103 罚没 | 纠纷执行方拿到不足一半：罚该类目当前影响力的 30%（至少 10 点）；为他担保（这一单或这个类目）的担保全部罚没一半；申诉改判后补 `restore`（执行方与担保人都恢复），并照常记这一单的收入——原来的罚没那条不动 |
| INF-104 撮合 | 候选人在任务类目的等级：熟手 +0.02、专家 +0.05、资深专家 +0.08，理由「「保洁」专家（平台影响力）」 |
| INF-105 担保 | 熟手以上；担保额合计 ≤ 本类目影响力的一半；为某一单作保要求对方报了名或承接了这一单；对方开工后锁住不能撤；类目担保 180 天到期自动释放（不奖励） |
| INF-106 快照 | 每天一次（job `/influence/jobs/snapshot`）：叶子 = sha256([user_id, 类目, 影响力])，排序后建树、父节点按排序拼接；根锚定进存证链 `influence.snapshot` |

## 3. 接口

| 编号 | 接口 | 说明 |
|---|---|---|
| INF-102 | `GET /influence/me` | 各类目等级、影响力、担保占用与可用、还差什么；最近 30 条变动；给出与收到的担保；规则一句话 |
| INF-107 | `GET /users/{id}/influence` | 对外：等级与大致影响力、多少人为他作保；不给明细；资料不公开、封禁、注销的 404 |
| INF-107 | `GET /influence/leaderboard?category=` | 某类目熟手以上（只列资料公开、未封禁）前 20 |
| INF-105 | `POST /influence/vouches`、`DELETE /influence/vouches/{id}` | 担保与撤回；被担保人收到通知 |
| INF-106 | `GET /influence/snapshots/latest`、`GET /influence/me/proof` | 最近快照；我的每一条附 Merkle 路径与服务端验算结果 |
| INF-106 | `POST /influence/jobs/snapshot` | 定时任务（job 令牌 + 单实例锁） |

错误码：`influence_vouch_self`、`influence_vouch_tier`、`influence_stake_exceeds`、`influence_vouch_task_mismatch`、`influence_vouch_exists`、`influence_vouch_closed`、`influence_vouch_locked`（`i18n.ts` 都有人话：为什么、怎么办）。

## 4. 两端

- **Web**：`/influence`（我的等级、还差什么、担保与撤回、类目排行、变动明细、快照与证明）；个人中心入口；别人的个人空间里「影响力」一块与「为他担保」。
- **App**：「我的 → 影响力与专家等级」同样五块；别人的空间里同样的一块与担保。
- 取不到（含老服务端没有这些接口）就不显示，不带崩页面。

## 5. 隐私、授权与边界

- 影响力不是钱：不能充值、提现、转让、兑换；SDK 也没有任何转让方法。
- 对外只给等级与取整的影响力、担保汇总；事件明细、担保占用、还差什么只给本人。
- 快照里存的叶子原值不对外，只用来给本人生成证明。
- 注销：本人的账本与给出的担保删除；别人为他作的担保释放（不罚没、不奖励）；数据导出含账本与担保。
- 罚没只由**已经发生的**纠纷裁决触发，AI 不参与判定。

## 6. 闸门与红验

19 处变异全部变红（`scratchpad/mut152.py` 的做法，逐条改坏 → 对应测试红 → 改回）：

| 闸门 | 红验 |
|---|---|
| 同一对人递减 | 去掉 `/ nth` → `test_same_pair_diminishes…` 红 |
| 只算已揭晓评价 | 去掉 `rating_applied` 过滤 → `test_ratings_count_only_after_reveal` 红 |
| 专家要实名、星级、近期无败诉 | 各去一个条件 → `test_tiers_need…`、`test_slash_has_a_floor…` 红 |
| 罚没比例、担保罚没、申诉恢复、败诉不挣 | 改比例 / 去掉恢复分支 / 去掉败诉判断 → `test_dispute_loss_slashes…` 红 |
| 担保额度、等级门槛、只能本人撤、开工锁住 | 各改一处 → `test_vouch_rules`、`test_dispute_loss_slashes…` 红 |
| 做成后释放并奖励 | 不释放 → `test_vouch_released…` 红 |
| 快照证明与防篡改 | 叶子去掉影响力 / 父节点不排序 → `test_snapshot_is_anchored…`、`test_merkle_proofs…` 红 |
| 对外隐私 | 去掉公开过滤 / 对外也给担保占用 → `test_public_view_and_leaderboard…` 红 |
| 撮合加分 | 清空加分表 → `test_matching_gives_tier_bonus…` 红 |
| 注销释放担保 | 改条件 → `test_erase_and_export` 红 |
| 不可转让 | `test_there_is_no_way_to_move_influence…`：influence 的写接口只能是担保、撤回、快照 job 三个 |
| 响应形状 | `test_responses_match_sdk_types`（Influence* 全部） |
| 两端 | `web/src/Influence.test.tsx`（错误提示、可用额度两处红验）、`app/influence.test.tsx` |
| 真浏览器 | `e2e_web.py`：打开 `/influence`，真服务端给出等级与规则、快照证明可取 |

## 7. 没做的

- **INF-110 公链锚定与端上独立验算**：现在树根写进平台自己的存证哈希链（可整链校验）；写到公链（或第三方时间戳服务）要外部账号与费用，记作「外」。
  客户端自己用 sha256 验算路径（不信服务端的 `verified`）要在 App 引入哈希库，排进后续批次。
- 担保人与被担保人之间的关联识别（同一设备、同一收款账户互相担保）：要先接风控的设备指纹数据。
- 影响力参与报名排序以外的权重（例如纠纷仲裁的陪审资格）：先看等级分布，再定。
