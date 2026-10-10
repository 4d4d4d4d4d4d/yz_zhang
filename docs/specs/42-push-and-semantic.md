# 42 兑现两句写了很久的注释（NTF / KB）

> 补需求回顾里查出的两条**降级实现**：推送通道与向量检索。
> 它们不是「没做」，是「做了个简化版，并在注释里写了一句『生产再说』」。

## 0. 这一批修的是什么

```python
# app/modules/notification/service.py:1
"""通知（NTF-004）：领域事件 → 站内信模板。生产追加 APNs/FCM/短信通道。"""

# app/modules/knowledge/service.py:102
"""CS-002 简化版检索（生产为向量检索 + LLM 生成，此处关键词匹配保证可测）。"""
```

两句话都从 MVP 写到现在。它们比「没实现」更隐蔽：**读代码的人会以为这是
已知的、受控的简化**，而实际上没有任何东西记录它们该在什么时候兑现。

### NTF-002 只存在于站内的提醒，和没有提醒差别不大

这条的代价是具体的，而且是我自己上一批造出来的：
V63 加了「答辩期将届满时提醒被诉方」，答辩期 48 小时，逾期即缺席裁决。
**但那条提醒只写进站内信。** 用户不主动打开 App 就看不到，
48 小时静默过去，他仍然失去了陈述机会——

V63 补的是「会提醒」，这一批补的是「提醒真的到得了人」。少了后一半，
前一半只是看起来完成。

### KB-011 悄悄退化的「语义检索」比没有更糟

关键词匹配本身不丢人，丢人的是**它自称是别的东西**。
这一路修过的缺陷里有一整类就是这个形状：声明与实际不符，而且写错了不报错。

## 1. 设计判断

**判断一：推送走发件箱，不在 `notify()` 里同步打第三方。**
通知常常是在业务事务里发出的（放款、托管、纠纷开案）。同步调用推送网关
意味着**一次网络抖动会把一笔放款回滚掉**。发件箱（EVT-021）本来就有重试、
死信、跨副本补做——推送白拿这些能力，而且天然不会拖垮业务。

**判断二：缺省实现不假装成功。**
`NoPush.send()` 返回 `delivered=0, reason="no_push_provider"`，
`LocalBagOfWordsEmbedding.semantic = False`，检索结果带 `degraded` 标志。
**把「其实没接」这件事一路透出到 API 响应与供应商面板**，
而不是让它在某个注释里待着。

**判断三：词袋哈希是管线的占位，不是语义的替代。**
我不把它说成「实现了语义检索」。它做到的是让**整条管线是真的**：
向量维度、索引落库、余弦排序、增量重建、模型切换检测。
接真实模型（任何 OpenAI 兼容的 `/v1/embeddings`）只改环境变量，
业务代码一行不动。这与本仓库所有其它供应商的三态形态一致。

**判断四：`embedding_model` 必须和向量一起存。**
换模型后旧向量不可比——拿两个模型的向量做余弦会得到一堆毫无意义的相似度。
存了模型名才能做**增量**重建；全表重跑在真实模型下是要花钱的。

## 2. 条目

### 推送（NTF-002 / IM-008）

- **NTF-010** `app/vendors/push.py`：`PushProvider` Protocol +
  `NoPush`（不发，如实上报）/ `SandboxPush`（形态真实，含失效令牌路径）/
  `HttpPushProvider`（通用网关，APNs/FCM/极光/个推同形）。
- **NTF-011** `device_tokens` 表：**令牌即主键**，重复注册幂等——
  App 每次启动都会注册，攒出重复行的后果是同一条通知推四遍。
- **NTF-012** 换账号登录同一台设备时令牌改归属。不改的话新用户的通知会推给
  上一个用户；共用手机场景下这是实打实的隐私泄露。
- **NTF-013** `notify()` 在写站内信之后 `publish("notification.created")`，
  由发件箱驱动推送。
- **NTF-014** 供应商回报的失效令牌落地置 `revoked`。设备卸载后令牌永久失效，
  不清理就会年复一年地推给不存在的设备，而通道按量计费。
- **NTF-015** 端点：`PUT/GET/DELETE /notifications/devices`；SDK 与 App 接上。
  App 侧 `getPushToken()` 现在返回 `null` 并**如实返回「拿不到」**，
  不编一个假令牌去污染服务端。

### 向量检索（KB-011 / KB-022 / CS-002）

- **KB-030** `app/vendors/embedding.py`：`EmbeddingProvider` +
  `LocalBagOfWordsEmbedding`（`semantic=False`）/ `HttpEmbedding`（OpenAI 兼容）。
- **KB-031** `knowledge_cards` 与 `faq_entries` 加 `embedding` +
  `embedding_model` 两列。
- **KB-032** `POST /knowledge/jobs/reindex`：**增量**重建，只补没有向量或
  模型已换的行；登记进 `app/core/jobs.py`（周期 1h）。
- **KB-033** `GET /knowledge/search?q=&kind=card|faq`：余弦排序，
  响应带 `semantic` / `degraded` / `model`。
- **KB-034** 没建索引时退化为词面命中，但 `degraded=True` **原样返回**。

## 3. 已知缺口

- **NTF-020 没有真机验证。** `SandboxPush` 与 `HttpPushProvider` 的形状是按
  APNs/FCM 的服务端接口写的，但本环境没有推送网关也没有真机，
  端到端只验到「调用发生了、失效令牌被清理了」。接真实通道后必须补一次真机验收。
- **NTF-021 App 的 `getPushToken()` 仍返回 null。** 需要 `expo-notifications`
  依赖与真机权限流程，而 `app/` 尚未纳入 CI（DSPR-042），加依赖无法验证。
- **NTF-022 短信通道未接入通知链路。** `SmsProvider` 在册（验证码在用），
  但「哪些通知值得花钱发短信」是运营决策，不在本批范围。
- **KB-040 缺省 embedding 不是语义模型。** 这是本批最重要的一句诚实说明：
  词袋哈希捕捉的是词面重合，语义能力与关键词匹配基本相当。
  管线是真的，模型不是——接真模型只改 `PLATFORM_EMBEDDING_PROVIDER=http`。
- **KB-041 没有向量数据库。** 余弦排序是全表扫描，卡片量上万后需要
  pgvector 或专用索引。当前规模下这不是瓶颈，但别忘了它。
- **KB-042 RAG 只做检索，不做生成。** `GET /knowledge/search` 返回的是
  片段，把片段喂给 LLM 生成答案那一步仍在 `decompose/llm.py` 之外。
