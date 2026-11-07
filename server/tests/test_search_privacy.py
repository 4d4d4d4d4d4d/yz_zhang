"""PRIV-060 / PRIV-061 搜索：接到界面上之前，先把它会公开的东西管住（101 号 spec）。

`search` / `searchSuggest` / `trendingTerms` 此前三端零调用。准备接上两端时
读了一遍服务端，发现两处**一旦有了界面就会变成事故**的问题：

1. **热词与联想原样公开任何人敲过的原始搜索串**——不要登录、不设门槛、不过审核。
   有人搜过「张三 13800001234」，任何人在框里打「张」都能看到它，一次就够。
   反过来，任何人反复搜同一句广告，就能把它推上公开的热词榜（搜索是 GET，
   写路径限流管不到它）。
2. **用户搜索不看隐私设置**：只排除了封禁。设了「资料不公开」的人照样被搜出来，
   连同技能与信用分；已注销的「已注销用户」也会出现在结果里。

它们今天没出事，只是因为没有任何界面调用这三个接口。
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile

from tests.conftest import auth, register


def _search(client, user, q):
    r = client.get("/api/v1/search", params={"q": q}, headers=auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def _people(n, client, base):
    return [register(client, f"1380009{base}{i:02d}", f"搜索者{i}") for i in range(n)]


# ------------------------------------------------- PRIV-060 公开的热词
def test_priv060_one_persons_search_is_never_public(client):
    """一个人搜过的词，**搜多少次都不公开**——次数可以被一个人刷出来，人数不行。"""
    u = register(client, "13800097001", "独自搜索的人")
    for _ in range(10):
        _search(client, u, "罕见的私人词")
    trending = client.get("/api/v1/search/trending").json()
    assert all(t["term"] != "罕见的私人词" for t in trending), trending
    assert "罕见的私人词" not in client.get("/api/v1/search/suggest", params={"q": "罕见"}).json()


def test_priv060_a_term_becomes_public_at_the_distinct_user_threshold(client):
    """到第 3 个不同的人才公开；返回的计数是**人数**。"""
    people = _people(3, client, "71")
    for p in people[:2]:
        _search(client, p, "上门保洁")
    assert "上门保洁" not in client.get("/api/v1/search/suggest", params={"q": "上门"}).json()

    _search(client, people[2], "上门保洁")
    assert "上门保洁" in client.get("/api/v1/search/suggest", params={"q": "上门"}).json()
    trending = {t["term"]: t["count"] for t in client.get("/api/v1/search/trending").json()}
    assert trending.get("上门保洁") == 3, trending


def test_priv060_identifiers_are_never_even_stored(client):
    """带手机号、身份证号、邮箱的搜索词**根本不记**——数据最小化在写入时做。"""
    from app.core.db import SessionLocal
    from app.modules.analytics.models import SearchQuery

    people = _people(3, client, "72")
    for p in people:
        for q in ("张三 13800001234", "110101199001011235", "zhang@example.com"):
            _search(client, p, q)
    db = SessionLocal()
    try:
        stored = [r.term for r in db.query(SearchQuery).all()]
    finally:
        db.close()
    for q in ("13800001234", "110101199001011235", "zhang@example.com"):
        assert not any(q in t for t in stored), f"身份标识被存下来了：{q}"
    assert "张" not in " ".join(client.get("/api/v1/search/suggest", params={"q": "张"}).json())


def test_priv060_moderated_terms_cannot_be_pushed_into_trending(client):
    """过不了内容审核的词不进热词榜——此前反复搜就能把它推上去。

    **两层各自钉住。** 红验时发现：把写入时的审核去掉，这条仍然是绿的——
    读取时还有一道审核把它挡在了公开结果外面。可 `log_search` 的 docstring
    写着「不记的两类」，那一半的承诺就没有任何东西在检查。
    所以这里同时断言**它根本没被存下来**。
    """
    from app.core.db import SessionLocal
    from app.modules.analytics.models import SearchQuery

    people = _people(4, client, "73")
    for p in people:
        _search(client, p, "代考包过")
    trending = [t["term"] for t in client.get("/api/v1/search/trending").json()]
    assert "代考包过" not in trending
    db = SessionLocal()
    try:
        assert db.query(SearchQuery).filter(SearchQuery.term == "代考包过").count() == 0, \
            "过不了审核的词被存下来了（写入时那一层没在拦）"
    finally:
        db.close()


def test_priv060_terms_stored_before_a_rule_change_are_still_filtered_on_read(client):
    """读取时那一层：词是很久以前记下的，而审核规则会更新。

    直接往表里放一条「当时还没被禁」的词（3 个不同的人），模拟规则更新之后——
    它不该出现在公开结果里。写入那一层拦不到它：它在规则更新之前就进来了。
    """
    from app.core.db import SessionLocal
    from app.modules.analytics.models import SearchQuery

    people = _people(3, client, "75")
    db = SessionLocal()
    try:
        for p in people:
            db.add(SearchQuery(term="刷单兼职", user_id=p["id"]))
        db.commit()
    finally:
        db.close()
    assert "刷单兼职" not in client.get("/api/v1/search/suggest", params={"q": "刷单"}).json()


def test_priv060_percent_is_not_a_wildcard(client):
    """用户打一个 `%` 不该匹配到所有词（autoescape）。"""
    people = _people(3, client, "74")
    for p in people:
        _search(client, p, "保洁阿姨")
    assert client.get("/api/v1/search/suggest", params={"q": "%"}).json() == []


# ------------------------------------------------- PRIV-061 搜人看隐私
def test_priv061_private_and_deleted_people_are_not_searchable(client):
    """与空间、公开资料同一条可见性规则。"""
    from app.core.db import SessionLocal
    from app.modules.account.models import User

    seeker = register(client, "13800097101", "找人的人")
    register(client, "13800097102", "可见的木工")
    private = register(client, "13800097103", "隐身的木工")
    gone = register(client, "13800097104", "离开的木工")
    client.patch("/api/v1/users/me", json={"privacy": {"profile_public": False}},
                 headers=auth(private))
    db = SessionLocal()
    try:
        db.get(User, gone["id"]).is_deleted = True
        db.commit()
    finally:
        db.close()

    names = [u["nickname"] for u in _search(client, seeker, "木工")["users"]]
    assert "可见的木工" in names, "正当结果都没有，这条测试什么都没验"
    assert "隐身的木工" not in names, "设了资料不公开的人被搜出来了"
    assert "离开的木工" not in names, "已注销的人被搜出来了"


def test_priv061_percent_does_not_list_every_user(client):
    """搜 `%` 不该把全站用户列出来。"""
    seeker = register(client, "13800097201", "找人的人")
    register(client, "13800097202", "某人")
    assert _search(client, seeker, "%")["users"] == []


# ------------------------------------------------- 迁移与一致性
def test_priv060_migration_purges_stored_identifiers_and_keeps_the_rest():
    """迁移删掉已经存下的身份标识类搜索词，其余不动。

    这是不可逆的——而 V118 那次我拒绝在迁移里合并聊天记录，理由也是不可逆。
    区别在于对象：那是用户的聊天记录；这是平台内部的统计日志，
    里面的身份标识本来就不该被存下来。
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/s.db"
        env = {**os.environ, "PLATFORM_DATABASE_URL": url, "PLATFORM_ENV": "sandbox"}
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "c1d220260005"],
                       cwd=root, env=env, check=True, capture_output=True)
        db = sqlite3.connect(f"{tmp}/s.db")
        for term in ("保洁", "张三 13800001234", "110101199001011235", "a@b.com", "跑腿"):
            db.execute("INSERT INTO search_queries (term, created_at) VALUES (?, '2026-10-01')", (term,))
        db.commit()
        db.close()

        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=root, env=env, check=True, capture_output=True)
        db = sqlite3.connect(f"{tmp}/s.db")
        left = sorted(r[0] for r in db.execute("SELECT term FROM search_queries"))
        cols = {r[1] for r in db.execute("pragma table_info(search_queries)")}
        db.close()
    assert left == ["保洁", "跑腿"], left
    assert "user_id" in cols


def test_priv060_migration_and_service_use_the_same_patterns():
    """迁移里抄了一份身份标识模式（迁移不 import 应用代码）。两份必须一致——
    第二份实现必然抄漏，所以这里钉住它。"""
    from app.modules.analytics.service import PII_PATTERNS

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "migrations", "versions",
                            "c1d220260006_search_query_user_id.py"), encoding="utf-8").read()
    ns: dict = {}
    exec(re.search(r"PII_PATTERNS = \(.*?\n\)", src, re.S).group(0), ns)  # noqa: S102
    assert tuple(ns["PII_PATTERNS"]) == tuple(PII_PATTERNS)
    _ = json  # 与其他迁移测试同一套导入
