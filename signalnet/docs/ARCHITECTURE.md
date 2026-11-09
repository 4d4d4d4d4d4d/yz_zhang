# SignalNet 技术架构

## 1. 总体分层

```
┌──────────────────────────────────────────────────────────────────────────┐
│ L3 组装/入口  node（轮次 + tick 时钟、重放）  cli（demo）                   │
│               store（SQLite）  api（HTTP）  sync（gossip）                 │
├──────────────────────────────────────────────────────────────────────────┤
│ L2 机制       reputation（PoS）  ranking（排序/算法/欠账）  ads（分账/托管） │
│               federation（hub 上限/监控）  jury（抽签）  classify（四分类/母题）│
│               disputes（申诉/举报）  governance（参数治理）                  │
├──────────────────────────────────────────────────────────────────────────┤
│ L1 数据对象   content  attestation（含 commit）  records（通用签名记录）     │
│               fingerprint（文本/媒体指纹、精确多索引）                       │
├──────────────────────────────────────────────────────────────────────────┤
│ L0 原语       crypto（DID/签名/密钥）  ledger（哈希链）                      │
└──────────────────────────────────────────────────────────────────────────┘
```

**分层规则（`harness/gate.py` 的 `layers` 门禁强制）**

- 只能依赖同层或更低层。
- `ranking → ads`、`reputation → ads`、`ranking → node` 是**禁止边**：广告在结构上无法影响排序与声誉（INV-2）。
- L0–L2 禁止 import `random/time/datetime/socket/uuid/...`：时间、随机数一律作为参数传入，保证可复算（INV-4）。`crypto` 生成密钥是唯一例外。
- 新增模块必须在 `harness/gate.py::LAYERS` 中登记层级，否则门禁失败。

## 2. 内容生命周期（生产模式）

```
publish（质押 5 声誉、查重、母题识别）
   │
tick ──► 抽签首轮陪审（种子 = 内容ID|轮次|日志 head）
   │        0~48h commit ─► 48~72h reveal ─► 72h tick 自动结算
   │                                           │
   │      揭示不足 ──► 二次机会（≤2 次）        ├─ 分类：原创/衍生/追随/搬运
   │                                           ├─ 共识 ≥0.7（L2 起需桥接）→ 晋级，下一 tick 开下一轮
   │                                           ├─ 读者信号背离 → 复审轮
   │                                           └─ 搬运 → 移出、罚没
   │
   └──► 30/180 天 复审 → 经典 / 过时降级
```

所有时间相关动作只由 `tick(now)` 触发，并写入日志，因此任何节点重放都得到同样的结果。

## 3. 数据流

```
Identity ──sign──► Content ──publish──► Node ──append──► Ledger
                                        │
Identity ──sign──► Attestation ─attest─►│ (ReputationBook.lock)
                                        │
                              settle ──►│ ReputationBook.compute (纯函数) → apply
                                        │
                     feed(now) ◄────────│ ranking.rank(RankInput[])  ← 无广告数据
                                        │   + 每 N 条插入一个标注的广告位
                                        │
                 view_ad ──────────────►│ AdExchange.record_view → split_revenue
                                        ▼
                         Ledger ──replay──► 另一个节点 → state_digest 相等
```

## 4. 关键设计决策

| 决策 | 理由 | 记录 |
|---|---|---|
| PoS 是声誉质押，不发币 | 避免投机与金融化，聚焦信息质量 | ADR-0001 |
| 加权中位数而非平均 | 抗离群值和少数合谋 | SPEC REQ-PS-002 |
| √质押 + 单人占比上限 | 抑制鲸鱼 | REQ-PS-003 |
| 金额用整数 micros | 避免浮点误差，保证守恒 | REQ-AD-003 |
| 日志是哈希链而非区块链 | M1 只需可审计和可重放，无需全局共识；M2 用 gossip 同步 | REQ-FD-002 |
| 核心库零网络依赖 | 机制可单测、可仿真；网络层只是 L3 适配器 | — |
| 同步 = 重新执行 | gossip 不信任对方状态，逐条重放并比对事件哈希 | REQ-NW-003 |
| 首轮陪审延迟到下一次 tick 抽签 | 防止作者反复改内容刷出有利陪审 | REQ-CS-002 |
| 两套配置 | 宽松模式便于仿真与实验；生产模式开启全部防护 | — |

## 5. 演进路线（技术）

```
M1 内核库（当前） ─► M2 单节点服务（HTTP API + SQLite）
                  ─► M3 多节点联邦（gossip 同步、hub 路由、数据迁移）
                  ─► M4 媒体与客户端（视频存储/转码、App、支付通道）
```

M2 规划的目录：

```
src/signalnet/
  store/        # L3 持久化适配器（SQLite），只依赖 node 的事件接口
  api/          # L3 HTTP 适配器（标准库 http.server 起步 → 后续可换 ASGI）
  sync/         # L3 gossip：交换 ledger head，增量拉取并 replay 验证
```

## 6. 仓库结构

```
signalnet/
├── AGENTS.md            # AI/人类贡献者的工作协议（先读这个）
├── CONTRIBUTING.md      # 入库流程与编码规范
├── TODO.md              # 手工待办 + harness 自动区
├── docs/
│   ├── VISION.md        # 愿景
│   ├── SPEC.md          # 需求真相源（门禁解析）
│   ├── ARCHITECTURE.md  # 本文件
│   ├── ROADMAP.md       # 里程碑与需求分解
│   └── adr/             # 架构决策记录
├── src/signalnet/       # 源码（分层见上）
├── tests/               # unittest，每个测试在 docstring 标注 REQ-ID
└── harness/
    ├── gate.py          # 入库门禁
    └── iterate.py       # 持续迭代传感器 → TODO.md
```
