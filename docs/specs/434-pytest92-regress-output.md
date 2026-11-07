# 434 pytest 9.2 兼容与回归输出留全失败

> 状态：本批实现（V461）。编号 TEST-090（供应商代理转发删除）、TEST-091（联调浏览器路径不写死版本号）、REG-004（回归输出留下每一条失败）。
> 来源：V458（bb8f712b）在新容器里的全量回归红了：后端「6 failed, 1 error」，真浏览器联调报 `No module named 'playwright'`。代码没变，是新容器装到了 pytest 9.2.0，也没有 Python 版 playwright。
> 只增不减：业务代码只给供应商代理加了一个转发；老断言都留着，只往上加。

## 0. 要解决的问题

- **pytest 9.2 的 monkeypatch 收尾报错（TEST-090）。**
  - `requirements.txt` 写的是 `pytest>=8.0`，GitHub CI 每次也会装到最新版，迟早一样红。
  - 9.2 起，monkeypatch 给实例记旧值时改读实例的 `__dict__`。
  - 供应商代理 `Guarded`（CONC-067）用 `__slots__`，自己没有 `__dict__`，读到的是被代理对象的，而类上定义的方法不在里面，于是记成「原来没有」。撤销时 pytest 就对代理做 `delattr`。
  - 代理以前只转发 `setattr`、不转发 `delattr`，结果报 `'Guarded' object has no attribute 'verify'`。
  - 那一次没撤销干净，打过补丁的方法留在供应商单例上，后面的测试（如沙箱托管闭环）跟着红。
- **联调写死了浏览器版本号（TEST-091）。** `e2e_web.py` 找的是 `chromium-1194`，新容器里是 `chromium-1243`。不带版本号的软链接 `/opt/pw-browsers/chromium` 一直都在。
- **回归只留后端最后 3 行（REG-004）。** 6 条失败在 `be.txt` 里只看得到 1 条，要知道是哪几条，还得再跑 45 分钟。

## 1. 业界怎么做（带来源链接）

透明代理要成对实现 `__getattr__ / __setattr__ / __delattr__`，否则对代理的删除不会落到被代理对象上。测试结果要留下完整日志，摘要只做索引。本轮没有引用外部报道链接。

## 2. 数据

不涉及。

## 3. 接口

不新增接口。

- `app/core/txguard.py`：`Guarded.__delattr__` 转发给被代理对象。
- `server/scripts/e2e_web.py`：先找 `/opt/pw-browsers/chromium`，再找老路径，都没有就用 Playwright 自己装的浏览器。
- `tools/regress.sh`：
  - 后端完整输出写进 `be.full.txt`；
  - `be.txt` 收下每一条 `FAILED` / `ERROR` 和最后的汇总行；
  - 判红规则不变。
- skill `regression`：写明新容器要先装齐依赖：
  - `python -m pip install -r server/requirements.txt ruff==0.15.8 playwright==<与 node 版一致>`；
  - 仓库根和 `app/` 各跑一次 `npm ci`。

## 4. 两端

不涉及界面：工程与测试基础设施。

## 5. 隐私、授权与边界

不涉及。

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|
| `server/tests/test_txguard_proxy.py`（2 条）：<br>对代理删属性落到被代理对象上；用 `pytest.MonkeyPatch` 给代理打补丁，撤销后方法恢复、被代理对象上不留东西 | 让 `__delattr__` 不转发（直接抛 AttributeError）：两条都红 |
| `server/tests/test_ci_portability.py` 新增 1 条：<br>真跑一遍 regress.sh 里的提取命令，6 条 FAILED、1 条 ERROR 和汇总行一条不少 | 把提取改成只留最后一条 FAILED：红 |
| `test_e2e_does_not_require_the_dev_container_browser` 扩展一句：先找不带版本号的软链接 | 去掉软链接那一项：红 |
| 本地复现 | `test_response_shape_sweep.py`、`test_sandbox_stubs.py` 等 6 个用到供应商代理的测试文件，在 pytest 9.2.0 下全过 |

## 7. 没做的

| 编号 | 内容 | 去处 |
|---|---|---|
| — | 不在 `requirements.txt` 里给 pytest 封顶 | 有意不做：兼容新版比钉旧版好，CI 用最新版正好能早发现 |
