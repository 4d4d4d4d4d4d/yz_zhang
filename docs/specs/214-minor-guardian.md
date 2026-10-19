# 214 未成年人服务对象的监护人关口与陪练看护资质

> 状态：本批实现（V242）。编号 SCN-144。
> 来源：212 号 spec 关口 G2、G3；BACKLOG V242。
> 只增不减：不勾「服务对象是未成年人」时发布的请求体与行为不变；已有受限类目（律师、电工、燃气）的资质规则不变，本批复用同一套。
> 写明的行为变化：`tasks` 加三列 `minor_involved`、`guardian_mode`、`guardian_consent_at`（迁移 c1d220260046）；新类目「陪练看护」（接单要无犯罪记录证明）；提交「无犯罪记录证明」时有效期必填、最长一年。

## 0. 要解决的问题

家长找人陪练、看护、接送孩子，平台以前和别的单一样处理：谁都能报名、不知道是不是单独相处。212 号定了两道关口：发单这一侧，监护人确认并选定「监护人在场」或「公开场所」；接单这一侧，要有平台审核通过、在有效期内的无犯罪记录证明。

## 1. 依据

见 212 号 spec 第 1 节（《未成年人保护法》第六十二条与教职员工准入查询制度）。平台不是用人单位，也接不进公检的查询渠道（「外」），所以做的是**审核本人交来的证明**这一步，并限制安排方式。

## 2. 数据

- `tasks.minor_involved`（布尔）、`tasks.guardian_mode`（`guardian_present` / `public_place`）、`tasks.guardian_consent_at`（监护人确认的时间）。多人多天单的名额继承这三项。**不存孩子的任何信息**（姓名、学校、照片都不收）。
- 类目「陪练看护」：`required_cert = 无犯罪记录证明`（沿用 `ADDED_CATEGORIES` 只补一次的做法）。
- 迁移在 SQLite 与 Postgres 上 `upgrade head` + `check` 通过。

## 3. 接口

| 接口 | 变化 |
|---|---|
| `POST /tasks` | 可选 `minor_involved`、`guardian_mode`、`guardian_consented`。勾了「服务对象是未成年人」：没选或选了别的安排 `minor_needs_guardian_mode`（「平台不允许和孩子单独相处的安排」）；没确认 `guardian_required`；没勾却带了安排或确认 `guardian_without_minor`。通过时记下监护人确认的时间 |
| 任务详情 | 多 `minor_involved`、`guardian_mode`（公开：接单前就要知道要求什么、在什么场合） |
| 报名 / 接单（`check_category_qualification`） | 服务对象是未成年人的单，不论类目都要求持有审核通过、在有效期内的「无犯罪记录证明」（`certification_required`，消息写明要什么证明）；「陪练看护」类目本身也要求 |
| `POST /users/me/certifications` | 提交「无犯罪记录证明」时有效期必填（`certificate_expiry_required`）、最长一年（`certificate_expiry_too_far`） |

新错误码进 `i18n.ts`。SDK：`Task.minor_involved` / `guardian_mode`、`TaskCreateInput` 三项、`GuardianMode`、`GUARDIAN_MODE_LABEL`；共享函数 `minorTaskLine`（详情上的一句话）、`minorPayload`（没勾一项都不带）。

## 4. 两端

- **Web** 发布页「服务对象是未成年人（陪练、看护、接送）」勾选：勾上后出现「监护人在场 / 在公开场所」单选与「我是孩子的监护人，或已经监护人同意」，下面一句说明（不允许单独相处、接单要证明、学科类家教不承接）。任务详情写一行「服务对象是未成年人 · 监护人在场 · 接单要有平台审核通过的无犯罪记录证明」。
- **App** 发布页与任务详情同样。
- 资质提交走两端已有的「提交资质」入口（REMEDY_UI：`certification_required` 已有补救入口）。

## 5. 隐私与边界

- 不收集孩子的信息；监护人确认只记时间。
- 无犯罪记录证明只给审核的管理员看，按资质材料原有的留存与注销规则处理（CERT-010 / CERT-011）。
- 平台不替任何一方判断「可不可靠」，只执行规则；举报与纠纷走原流程。

## 6. 闸门与红验

`server/tests/test_minor_guardian.py` 5 条；`packages/core/src/minor.test.ts` 2 条；`web/src/OnBehalf.test.tsx` 加 2 条；`app/onBehalf.test.tsx` 加 2 条；响应形状闸门覆盖新字段。

15 处变异（`scratchpad/mut242.py`）13 处首轮变红；「陪练看护类目不要求证明」（用例里的单都勾了未成年人）与「App 详情不写这一行」首轮存活，补了「类目本身就要证明」与 App 详情用例后变红。

## 7. 没做的

| 编号 | 内容 | 去向 |
|---|---|---|
| SCN-145 | 说明里提到孩子却没勾「服务对象是未成年人」时提醒发单人（现在只在任务画像里提示风险，不拦） | 已做（V243，215 号） |
| SCN-146 | 212 号 G2 里的「上门回报必选」：服务对象是未成年人的线下单要求按次回报（V203），本批没做 | 欠 |
| — | 直接查询犯罪记录 | 外（公检渠道） |
