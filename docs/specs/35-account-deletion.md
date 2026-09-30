# 35 账号注销的资金与个人信息闭环（ACCDEL）

> 对应 `POST /api/v1/users/me/deactivate`（ACC-006），以及 `docs/specs/26-legal-enforceability.md`
> LAW-032 里那句「删除权入口：`POST /users/me/deactivate`」。

## 0. 这一批修的是什么

注销是**不可逆**的：账号被标记 `is_deleted`、手机号改写、全部会话吊销，
此后 `get_current_user` 一律 403，密码登录一律 400。
它是全站唯一一个「用户主动把自己锁在门外」的操作。

用探针跑了一遍，发现三件事。

### ACCDEL-001 冻结中的钱可以被注销掉

闸门只看 `available_cents`：

```python
acct = wallet.get_or_create(db, user.id)
if acct.available_cents > 0:
    raise conflict("钱包仍有余额，请先提现", "balance_remaining")
```

钱包是**三态**的（可用 / 托管 / 冻结），这里只看了第一态。探针实测：

```
WITHDRAW:   200 {'status': 'pending_review', 'available_cents': 0, 'frozen_cents': 1500000}
WALLET:     {'available_cents': 0, 'escrow_cents': 0, 'frozen_cents': 1500000}
DEACTIVATE: 200 {'deleted': True}
```

一笔 ¥15,000 的大额提现进了人工复核（AML-001），钱从可用挪到冻结，
可用归零——于是注销闸门认为「没钱了」，放行。

然后复核有两种结局：

- **批准**：钱按 `decide_withdraw` 打到收款账户，用户其实拿到了，但全程看不见；
- **驳回**：`acct.available_cents += req.amount_cents`，¥15,000 退回到一个
  **再也登不上、手机号已被改写、连密码登录都被拒**的账户里。钱永久搁浅。

驳回是常态而不是意外——大额提现进人审的全部意义就是它可能被驳回。
换句话说：这条路不是极端情况才踩得到，它是 AML 复核的正常出口之一。

### ACCDEL-002 拦截条件用的是「手抄的状态列表」，不是钱本身

```python
Contract.status.in_(["pending_signatures", "signed", "funded"])
...
Dispute.status == "open"
```

两张列表都是手抄的白名单，抄漏了不会有任何东西报错。实际已经抄漏了一个：
`dispute.status` 还有 `"appealed"`（申诉复核中，`appeal-verdict` 会**重新分账**），
它不在拦截条件里。`app/modules/dispute/models.py` 上那行注释

```python
status: Mapped[str] = mapped_column(String(20), default="open")  # open/resolved/settled
```

自己也漏了 `appealed`——注释和代码同时错，且互相印证，这正是最难发现的一种错。

这是我在前几批反复遇到的同一类缺陷：**写错了不会报错的声明**。

### ACCDEL-003 注销后银行卡号和持卡人姓名原样留在库里

```
PAYOUT ACCOUNT AFTER DELETE: ('6222021234567890123', '张三')
USER AFTER DELETE: real_name='' is_verified=True
```

`users.real_name` 被小心地清成了 `""`，而 `payout_accounts` 里
**一模一样的姓名加一张完整卡号**被原样留下。

不是「该不该留」的问题——是**没有人做过这个决定**。
注销时清哪些字段，是一段手写的赋值序列：

```python
user.phone = f"deleted:{user.id}"
user.nickname = "已注销用户"
user.real_name = ""
user.bio = ""
user.lat = None
user.lng = None
```

六行，凭作者当时想得起来的字段。`skills` / `interests` / `certifications` /
`privacy` / `city` / `referral_code` 全部留着；`is_admin` 也留着
（注销一个管理员账号，管理员标记还在）。以后每加一个字段，
默认行为都是「留下」，而且不会有任何测试变红。

## 1. 设计判断：不能一删了之

直觉上「用户行使删除权 = 全删」。**这是错的，而且删过头本身违法。**

- 《反洗钱法》第十九条：客户身份资料自业务关系结束当年计起、交易记录自交易
  记账当年计起，**至少保存五年**。
- 《个人信息保护法》第四十七条给删除权写了例外：
  「**法律、行政法规规定的保存期限未届满**」的，不删除，但应当停止处理。

所以正确的形态不是「删」也不是「留」，是**逐字段的三选一**：

| 处置 | 含义 | 例子 |
|---|---|---|
| `ERASE` | 清空/置默认。没有任何法定留存义务的标识与画像 | 简介、技能、兴趣、位置、隐私设置、密码哈希 |
| `MASK` | 脱敏保留。够反洗钱调档与对账，**不足以再用于业务** | 真实姓名 `张*`、卡号 `6222****0123` |
| `RETAIN` | 原样保留。法定义务、对方当事人的凭证、或系统主键 | 交易流水、证件摘要、信用分、封禁标记 |

关键不在这张表怎么填，而在**它必须是一张显式的表**：
新增一个字段时，作者被逼着做一次决定，而不是让它默默地被留在库里。

## 2. 条目

### 闸门

- **ACCDEL-010** 注销前的资金闸门以**钱包三态之和**为准，而不是任何一个单态。
  `available + escrow + frozen > 0` 一律拒绝。
- **ACCDEL-011** 三个态各自给出**可执行**的指路，并在一条消息里**一次说全**，
  避免用户逐个撞墙：可用→去提现；托管→等合约结算；冻结→等复核/纠纷处理完成。
  错误码 `funds_remaining`。
- **ACCDEL-012** 合约与纠纷的拦截判断改为**反向**：声明「资金已彻底出账的终态」
  集合，不在集合里的一律视为进行中。
  - `contract.models.SETTLED_STATUSES = {released, split, refunded, cancelled}`
  - `dispute.models.CLOSED_STATUSES = {resolved, settled}`
  以后新增一个状态，忘了登记的方向是「**多拦一次注销**」，而不是「放走一笔钱」。
  失败要往安全的一侧倒。
- **ACCDEL-013** `appealed` 纠纷必须拦截——申诉复核会重新分账，
  当事人此刻注销等于放弃一笔还没算完的钱。

### 个人信息处置

- **ACCDEL-020** 注销时的字段处置由 `app/modules/account/deletion.py` 里的
  `USER_DISPOSITION` / `PAYOUT_DISPOSITION` 两张表**声明式**给出，
  `erase_personal_data()` 是唯一的执行入口。
- **ACCDEL-021** 处置表必须**逐列覆盖**模型，不多不少。多写一列（模型已删）
  或漏写一列（模型新增）都要红。
- **ACCDEL-022** `real_name` 由「清空」改为**保留姓氏 + 掩码**（`张*`）：
  清空既不满足反洗钱的身份资料留存，也没给隐私多买到什么——
  `id_digest` / `id_masked` 本来就留着。
- **ACCDEL-023** `payout_accounts.account_no` 掩码为 `6222****0123`、
  `holder_name` 掩码为姓氏 + `*`。掩码后**不足以发起打款**，
  这是有意的：注销后不应再有任何资金能流向这张卡。
- **ACCDEL-024** `is_admin` 在注销时置 `False`。注销一个管理员账号却把管理员
  标记留着，是把一个不可登录的账号留成了一枚定时炸弹（日后若有任何路径
  能复活账号，它复活成管理员）。
- **ACCDEL-025** `is_banned` **不清**。注销不是洗白封禁的手段。
- **ACCDEL-026** `referral_code` 清空：注销后这个码不该还能被别人填。
- **ACCDEL-027** 信用分与评价聚合（`credit_score` / `rating_*` /
  `tasks_completed`）保留：它们是**交易对手方**的凭证，不是注销者一个人的数据。

### 不变量

- **ACCDEL-030** 注销后钱包三态必须全为 0（由 ACCDEL-010 保证），
  测试直接断言这条不变量，而不是断言某几个 409。
- **ACCDEL-031** 注销**不改变**五条资金对账不变量（25 号 spec）。
- **ACCDEL-032** 注销后 `payout_accounts` 全表里不得再出现属于已注销用户的
  完整卡号（连续 12 位以上纯数字即判定为未脱敏）——扫全表，
  而不是只看刚注销的那一行。

## 3. 已知缺口

- **ACCDEL-040 手机号被改写而非掩码。** 现行实现把 `phone` 改写成
  `deleted:<id>`，号码本身释放（本人可用同号重新注册，这是好的），
  但反洗钱要求的「客户身份资料」里，联系方式这一项就此丢失。
  当前由 `id_digest` + `id_masked` + 掩码后的 `real_name` 承担身份资料留存。
  接持牌机构存管（FIN-052）后应改为「掩码保留 `138****5555` + 释放唯一索引」，
  需要加列与迁移，本批不做。
- **ACCDEL-041 没有留存期到期后的真删除。** 五年期满应当真正物理删除
  `MASK`/`RETAIN` 里属于个人信息的部分。需要一个按年扫描的 job，本批不做。
- **ACCDEL-042 注销不撤回已发布的内容。** 动态/评价/求助帖仍以「已注销用户」
  署名留存。这符合「对方当事人凭证」的取向，但没有给用户一个
  「注销并删除我发布的内容」的选项。
