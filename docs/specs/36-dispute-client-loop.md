# 36 纠纷的当事人闭环（DSPC）

> 对应 11 号 spec 的 DSP-005（两造兼听）、DSP-008（申诉复核），
> 以及 `app/modules/dispute/router.py` 全部当事人侧端点。

## 0. 这一批修的是什么

纠纷开出来以后，**当事人在客户端上是哑的。**

`packages/core/src/client.ts` 与 `web/src/`、`app/` 全文搜索 `statement` / `答辩`：
**零命中**。七个当事人侧端点里，客户端只接了一个：

| 端点 | 作用 | SDK | UI |
|---|---|---|---|
| `POST /tasks/{id}/disputes` | 发起纠纷 | ✅ | ✅ |
| `GET /disputes/{id}` | 看这场纠纷 | ❌ | ❌ |
| `POST /disputes/{id}/statements` | **答辩 / 举证** | ❌ | ❌ |
| `GET /disputes/{id}/statements` | 看双方陈述 | ❌ | ❌ |
| `POST /disputes/{id}/settlement` | 和解提案 | ✅ | ❌ |
| `POST /disputes/{id}/settlement/accept` | 接受和解 | ✅ | ❌ |
| `POST /disputes/{id}/appeal` | 申诉 | ❌ | ❌ |

也就是说：**唯一能做的动作是把纠纷开出来。** 开完之后资金冻结、任务转
`disputed`，然后双方都只能干等管理员出决定。和解的两个 SDK 方法写好了，
但没有任何界面调用——**死方法**，和没写一样。

### DSPC-001 服务端把「两造兼听」当成硬性前置，而客户端交不出这个前置

```python
# issue_verdict
if not _respondent_had_voice(db, dispute, task):
    raise conflict(f"被诉方尚未答辩且答辩期（{settings.DISPUTE_RESPONSE_HOURS} 小时）未过，暂不可裁决",
                   "response_window_open")
```

```python
# _respondent_had_voice
spoke = db.query(DisputeStatement).filter(..., user_id == respondent_id).first()
if spoke:
    return True
return utcnow() >= dispute.created_at + timedelta(hours=settings.DISPUTE_RESPONSE_HOURS)
```

被诉方永远不可能 `spoke`——**没有任何客户端能写入 `DisputeStatement`**。
所以这个判断的第一条分支在生产里是死代码，每一次都落到第二条：等满 48 小时。

后果不是「慢一点」，是**平台上线后的每一份处理决定都是缺席裁决**：
被诉方从未获得陈述的手段，而平台的审计记录会显示 100% 的纠纷在
「被诉方无陈述」的状态下结案。DSP-005 整条就是为了防止这件事，
它写在服务端、有测试覆盖、**且完全无法实现**。

### DSPC-002 被诉方连这场纠纷在哪都找不到

纠纷受理时发的通知是：

```python
def _on_dispute_opened(db, payload):
    for uid in payload.get("parties", []):
        notify(db, uid, "task", "纠纷已受理",
               "相关资金已冻结，请在 48 小时内协商或提交证据")
```

三个问题叠在一起：

1. **「提交证据」没有入口**——就是上一条；
2. 通知里**没有 `dispute_id`**，而全站没有任何「按任务查纠纷」的端点。
   发起方还能从 `openDispute` 的返回值里拿到 id，**被诉方一无所有**：
   他知道任务 #17 有纠纷，仅此而已；
3. 那个 **`48` 是硬编码的字面量**，不是 `settings.DISPUTE_RESPONSE_HOURS`。
   运维改了配置，通知会继续理直气壮地说 48——又一句写错了不会报错的话。

### DSPC-003 「能不能申诉」的判断只长在服务端

`appeal` 端点有三个条件（`status == "resolved"`、未申诉过、在
`APPEAL_WINDOW_DAYS` 窗口内）。客户端要画这个按钮，就得把这三条**再实现一遍**，
而 `_dump` 连 `resolved_at` 都不返回——客户端根本算不出窗口。
于是要么不画按钮（现状），要么画一个会 409 的按钮。

## 1. 设计判断

**判断一：这是 V59 那个缺陷的第二次出现，所以这次要留下机器闸门。**
V59 修的是「服务端竖起人机验证门、没有客户端能过」。这次是
「服务端要求两造兼听、没有客户端能开口」。同一个形状出现两次，
说明靠人记得同步客户端是不成立的——必须有测试盯着。

但 V60 的教训同样适用：**闸门本身不能是一个写错了不会报错的东西。**
我先试过用正则扫 `client.ts` 统计覆盖率，两次得到的数字（46 / 78 / 152）
都不一样——模板字符串、跨行泛型、查询串拼接都能骗过正则。
一个会漏报的检查器去防漏报，是自欺。

所以闸门做成**枚举 + 字面量匹配**，不做通用解析：
从纠纷路由里按依赖自动挑出「当事人侧端点」（`get_current_user`，
排除 `require_admin` 与 `/jobs/`），要求每一条的路径模板**作为字面量**
出现在 `client.ts` 里。枚举来自路由本身所以不会抄漏，
断言是精确子串所以不会误判。代价是只覆盖这一个模块——
但这个模块正是伤害具体的地方，宽而不准的检查没有价值。

**判断二：`appealable` 由服务端算，端点与按钮共用同一个判断。**
不是「顺便返回个字段」——是不允许同一条规则有两份实现。

## 2. 条目

### 让被诉方能找到并进入这场纠纷

- **DSPC-010** 新增 `GET /tasks/{task_id}/dispute`：当事人（与管理员）可按任务
  取回纠纷；无纠纷返回 404。这是被诉方从「通知说任务 #17 有纠纷」走到纠纷
  本身的**唯一**一条路。
- **DSPC-011** `_dump` 增加客户端算不出来的事实：
  `respondent_id`、`respondent_spoke`、`response_deadline`（ISO）、
  `resolved_at`、`appealable`。
  答辩期长度是服务端配置，客户端不该猜，也不该硬编码。
- **DSPC-012** `dispute.opened` 通知携带 `dispute_id`，且小时数取自
  `settings.DISPUTE_RESPONSE_HOURS` 而不是字面量 `48`。

### 让当事人能开口

- **DSPC-020** SDK 补齐四个方法：`dispute(id)` / `disputeByTask(taskId)` /
  `disputeStatements(id)` / `addDisputeStatement(id, content, attachments?)` /
  `appealDispute(id)`。
- **DSPC-021** Web 在任务详情里给出纠纷面板：状态、事由、双方陈述时间线、
  **答辩输入框**（并显示答辩截止时间）、和解提案与接受、结案后的申诉入口。
  和解的两个 SDK 方法此前是死方法，这里把它们接上。
- **DSPC-022** 答辩框在纠纷结案后消失（服务端本来就会 409，
  但不该让用户写完一段话才被拒）。

### 单一实现

- **DSPC-030** `appealable` 与 `POST /appeal` 的准入必须是**同一个函数**。
  测试双向对齐：`appealable` 为真时端点必须放行，为假时端点必须拒绝。

### 机器闸门

- **DSPC-040** 纠纷模块的**当事人侧**端点，路径模板必须逐条出现在
  `packages/core/src/client.ts` 里。枚举来自 FastAPI 路由（不会抄漏），
  断言是字面量子串（不会误判）。管理员端点与 job 端点显式排除。
- **DSPC-041** 不做通用的「全站端点 ↔ SDK」漂移检查：正则解析 TS 不可靠，
  一个会漏报的检查器比没有检查更糟。要扩到别的模块，就照 DSPC-040 的形状
  一个模块一个模块地加。

## 3. 已知缺口

- **DSPC-050 App（React Native）侧仍只能发起纠纷**，没有答辩界面。
  `app/App.tsx` 是骨架，本批只补 Web；SDK 已经就位，接上是纯 UI 工作。
- **DSPC-051 证据附件（`attachments`）在 Web 面板里只读**。
  上传走 `POST /files`，与答辩表单的串接留到文件模块那一批。
- **DSPC-052 答辩期届满前的提醒没有**。现在只有开案时一条通知；
  被诉方若不看通知，48 小时静默过去就变成缺席裁决。
  应在截止前若干小时补一条提醒（需要一个新 job）。
