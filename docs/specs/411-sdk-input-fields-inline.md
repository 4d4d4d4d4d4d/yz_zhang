
# 411 SDK 入参字段漏发闸门扩到内联类型与 camelCase 字段

> 状态：本批实现（V438）。编号 CLI-090b。
> 来源：上一批（V437，410 号）「没做的」：入参是内联对象类型的方法还没扫。扩的时候又发现上一批的扫描器自己有个盲区：
> - 字段名只认小写下划线；
> - camelCase 的字段（如 `holderName`、`dailyQuota`）会被悄悄跳过，等于没查。
>
> 只增不减：闸门扫得更全，不改任何接口。

## 0. 要解决的问题

- `submitCertification(input: { name; holderName; certNumber; … })`、`approveApiQuotaRequest(id, opts: { note?; dailyQuota?; days? })` 这类内联对象入参，同样会出现「入参里有、请求里没发」的情况。
- 扫描器只认小写字段名：只要字段名里有大写字母，这个字段就不会被检查。

## 1. 业界怎么做（带来源链接）

同 410 号：静态检查兜底。闸门自己也要红验，确认扫描器真的看得见要查的东西。本轮没有引用外部报道链接。

## 2. 数据

不涉及。

## 3. 接口

不改接口。`server/tests/test_sdk_input_fields.py` 两处改动：

- **内联类型**：签名里 `param: { … }` 的内联对象类型，按同一条规则查。
- **字段名**：从只认小写下划线，改为认任意标识符（camelCase 也认）。

现在扫到的方法数：

| | 方法数 |
|---|---|
| 扩之前 | 6 |
| 扩之后 | 24（新增内联类型 18 个） |

全部发全，没有发现现存的漏发。

## 4. 两端

不涉及界面：工程闸门。

## 5. 隐私、授权与边界

不涉及。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_sdk_input_fields.py`：<br>扫描器看得到内联类型方法（`submitCertification`、`approveApiQuotaRequest`），且总数不少于 20；新增 1 条红验（内联类型少发 `dailyQuota` 要报，camelCase 接口少发 `certNumber` 要报） | 把 `approveApiQuotaRequest` 请求体里的 `dailyQuota` 那一行删掉，闸门变红；改回变绿 |

## 7. 没做的

没有新增欠账。
