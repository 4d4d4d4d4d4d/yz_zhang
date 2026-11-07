# 39 上传图片的内容审核与处置（UMOD）

> 补 37 号 spec 的 FILE-031（`POST /files` 不调 `MODERATION_PROVIDER`）
> 与 FILE-032（没有删除入口）。

## 0. 这一批修的是什么

平台有内容安全供应商抽象、有举报流程、有审核队列、生产启动自检把
`moderation` 列为 P0 能力——**但图片从来不过审核**。

全仓唯一一处调用是：

```python
# app/modules/task/service.py
result = get_provider("moderation").check("text", text)
```

只有任务文本。而 `check()` 的签名第三个参数就叫 `media_urls`，
`LocalModerationProvider` 里甚至专门为它写了分支：

```python
if media_urls:
    # 本地实现看不了图/视频——明确标记为需人工复核，而不是假装通过
    return VendorResult(..., status="review", data={"reason": "media_not_inspectable"})
```

**这段分支从来没有被执行过**，因为没有任何调用方传 `media_urls`。
接口预留了、桩实现写好了、生产自检拦着不让用 mock——唯独没人调用。
这又是同一个形状：**建好了却没接上**。

而 V62 刚刚把「这张图是谁传的」落了库。那一批的理由就是
「归属落库后处置才成为可能」——**处置就是这一批**。没有这一批，
V62 建的那张表只是一张没人查的表。

## 1. 设计判断

**判断一：`reject` 拦截，`review` 放行进队列。**
`review` 的语义是「机器看不了/不确定，交给人」，不是「拒绝」。
把 `review` 当拒绝会让**所有本地/沙箱部署完全无法上传图片**
（本地实现对任何图片都返回 `review`），那不是安全，是瘫痪。

**判断二：供应商故障时 fail open 进人审队列，而不是 fail closed 拒绝上传。**

这是本批唯一一个我犹豫过的判断，所以写清楚理由。
内容安全的常规直觉是「宁可错杀」，但这里的上传物主要是**交付凭证与纠纷证据**。
`docs/OPERATIONS.md` 自己写着：

> 而交付凭证传不上去等于没有证据。

内容安全供应商抖一下，代价就是执行者在纠纷里拿不出现场照片——
**这个代价落在被侵害方身上，而不是落在违规者身上**。
所以故障时标 `review` 放行、进人审队列：既没有放弃审核，也没有让
第三方的可用性决定一个人能不能自证。

对外发布的内容（动态/博客）不适用这条——那条路走的是另一个入口，
本批不动。

**判断三：处置要真的删得掉文件。**
V62 用硬链接实现去重，命名条目各自独立，所以删一个名字不影响别人。
这一批把 `LocalStorageProvider.delete(name)` 补上——它同时是
ACCDEL-041（留存期满物理删除）将来要用的同一个原语。

**判断四：被拒的上传要告诉上传者。**
悄悄删掉文件、让 `<img>` 变成裂图，是最差的一种处理。

## 2. 条目

- **UMOD-010** `POST /files` 落盘后调用
  `moderation.check("image", "", [url])`，走 `vendor_base.call`
  （沿用既有的幂等/熔断/留痕）。
- **UMOD-011** `reject` → 删除命名条目、不落 `uploaded_files`、返回 400
  `moderation_rejected`，消息说明命中的标签。
- **UMOD-012** `review` → 正常返回 URL，`uploaded_files.moderation_status`
  记为 `review` 并记下标签，进管理员队列。
- **UMOD-013** 供应商异常（`VendorError`/熔断）→ 视同 `review` 放行，
  并把原因记进 `moderation_labels`，**不因第三方故障拒绝上传**。
- **UMOD-014** `uploaded_files` 新增 `moderation_status` / `moderation_labels`
  两列（迁移），并同步进 V60 的处置表（两列均 `RETAIN`：
  这是处置记录，属于平台的审核留痕）。

### 管理员处置

- **UMOD-020** `GET /admin/uploads/pending`：列出 `review` 状态的上传，
  含上传者、时间、命中标签、URL。
- **UMOD-021** `POST /admin/uploads/{name}/resolve`（`action=pass|reject`）：
  - `pass` → 状态改 `pass`，记审计；
  - `reject` → **物理删除文件** + 状态改 `reject` + 通知上传者 + 记审计。
- **UMOD-022** 通知上传者用的是明确文案（「你上传的一张图片因违反平台规范
  已被移除」），不是静默删除。

### 存储原语

- **UMOD-030** `LocalStorageProvider.delete(name)`：只删命名条目，
  不动 `blobs/<sha256>`。别人的名字仍然有效——这正是 V62 用硬链接的目的。
- **UMOD-031** 删除是幂等的：删一个不存在的名字返回 `False` 而不是抛错。

### 不变量

- **UMOD-040** 被拒的上传**不留任何痕迹**：文件不在、`uploaded_files` 无行。
- **UMOD-041** 甲的图被删，乙上传过的同一份内容仍然读得到。
- **UMOD-042** `media_urls` 真的被传下去了——断言供应商收到的
  第三个参数非空。这条专门防「又一次建好了没接上」。

## 3. 已知缺口

- **UMOD-050 没有主动复扫。** 只在上传时审一次。供应商模型更新后
  存量图片不会被重审，需要一个按批扫描的 job。
- **UMOD-051 `review` 队列没有 SLA。** 没有超期升级，也没有「积压多少条」
  的告警。纠纷有 DSP-009，这里没有对应物。
- **UMOD-052 拒绝只删文件，不追溯引用。** 图片 URL 可能已经写进
  `ProgressLog.images` 或纠纷证据，删除后那里会留下失效链接。
  正确做法是同时标记引用方，本批不做。
