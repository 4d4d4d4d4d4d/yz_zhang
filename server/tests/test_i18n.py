"""I18N 国际化机制（55 号 spec）。

这一批**刻意不做**全站文案抽取（服务端 382 条中文消息 + Web 侧约 1197 处
中文字面量）。理由写在 spec 第 0 节，核心是：

    **没有第二个语种可以验证。** 抽完之后唯一能证明「没抽坏」的办法是
    人肉点一遍全站，而一次抽错要等真上了第二语种才暴露。
    一个无法验证的大改动，不是进展，是把风险推到以后。

所以这一批做**机制**，以及那条真正关键的判断——
**错误的稳定契约是 `code`，不是 `message`**。
"""
import ast
import json
import pathlib
import re

from app.core.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, resolve_locale

ROOT = pathlib.Path(__file__).resolve().parents[2]
I18N_TS = ROOT / "packages/core/src/i18n.ts"

ERROR_FUNCS = {"bad_request", "conflict", "forbidden", "not_found"}
GENERIC_CODES = {"bad_request", "conflict", "forbidden", "not_found"}


# ------------------------------------------------------------- 解析 TS 侧的表
def _ts_block(name: str, pattern: str) -> str:
    src = I18N_TS.read_text(encoding="utf-8")
    m = re.search(pattern, src, re.S)
    assert m, f"没找到 {name}——正则失配时必须失败，不能返回空集"
    return m.group(1)


def client_catalog() -> dict[str, str]:
    body = _ts_block("ERROR_MESSAGE_ZH",
                     r"export const ERROR_MESSAGE_ZH: Record<string, string> = \{(.*?)\n\};")
    out = {}
    for line in body.splitlines():
        line = line.split("//")[0]
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*'(.*)',\s*$", line)
        if m:
            out[m.group(1)] = m.group(2)
    assert len(out) >= 150, f"只解析出 {len(out)} 条文案，正则多半失配了"
    return out


def server_worded_codes() -> set[str]:
    body = _ts_block("SERVER_WORDED_CODES",
                     r"export const SERVER_WORDED_CODES: string\[\] = \[(.*?)\n\];")
    codes = set(re.findall(r"'([a-z0-9_]+)'", body))
    assert len(codes) >= 20, f"只解析出 {len(codes)} 条，正则多半失配了"
    return codes


# --------------------------------------------- 扫服务端真正能抛出的错误码
def server_codes() -> dict[str, bool]:
    """返回 {code: 是否存在静态（非拼接）消息}。"""
    found: dict[str, bool] = {}
    for p in (ROOT / "server" / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name not in ERROR_FUNCS:
                continue
            msg_node = node.args[0] if node.args else None
            code = None
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                code = node.args[1].value
            for kw in node.keywords:
                if kw.arg == "code" and isinstance(kw.value, ast.Constant):
                    code = kw.value.value
                if kw.arg == "message":
                    msg_node = kw.value
            if not isinstance(code, str):
                code = name
            is_static = isinstance(msg_node, ast.Constant) and isinstance(msg_node.value, str)
            found[code] = found.get(code, False) or is_static
    return found


# ------------------------------------------------------ I18N-001/002/040 对齐
def test_i18n040_scanner_fails_loudly_rather_than_returning_empty():
    """扫描器自己不许静默失败——SYNC-003 立下的规矩。"""
    codes = server_codes()
    assert len(codes) >= 200, f"只扫到 {len(codes)} 个错误码，AST 扫描多半失效了"
    for known in ("insufficient_balance", "certification_required", "invalid_scope"):
        assert known in codes, f"{known} 没扫到，扫描器失效了"


def test_i18n001_every_server_error_code_has_client_text_or_is_declared_dynamic():
    """服务端能抛出的每个码，客户端要么有文案，要么**显式声明**要用服务端消息。

    与 SYNC-002（账本科目 ↔ SDK 文案）同一条规矩。少一条的后果不会报错，
    只会让用户看到一个英文标识符或一句空话。
    """
    catalog, dynamic = client_catalog(), server_worded_codes()
    missing = [c for c in server_codes() if c not in catalog and c not in dynamic]
    assert not missing, (
        f"这些错误码客户端既没有文案、也没声明为「用服务端消息」：{sorted(missing)}"
    )


def test_i18n002_client_catalog_has_no_codes_the_server_cannot_raise():
    """反方向：客户端多出的码说明服务端删过，表该跟着清。"""
    catalog = client_catalog()
    # 四个兜底码有意常驻：`errorMessage` 在什么都匹配不上时回落到
    # `ERROR_MESSAGE_ZH.bad_request`，所以它必须在表里，
    # 哪怕服务端的每一处调用都显式传了更具体的码。
    known = set(server_codes()) | server_worded_codes() | GENERIC_CODES
    extra = sorted(set(catalog) - known)
    assert not extra, f"这些码服务端已不再抛出：{extra}"


def test_i18n001_dynamic_codes_are_not_given_made_up_text():
    """**只有拼接消息的码，客户端编不出等价文案，所以不编。**

    把它们列出来而不是让它们悄悄落进兜底分支，是为了让「哪些还没本地化」
    可数、可查——一个说不清自己覆盖了多少的翻译表，等于没有覆盖率。
    """
    catalog, dynamic = client_catalog(), server_worded_codes()
    overlap = sorted(set(catalog) & dynamic)
    assert not overlap, f"这些码被声明为「用服务端消息」，却又编了一条文案：{overlap}"

    codes = server_codes()
    for code in dynamic:
        assert code in codes, f"{code} 声明在 SERVER_WORDED_CODES 里，但服务端不抛它"
        assert codes[code] is False, (
            f"{code} 其实有静态消息，应该进文案表而不是声明为动态"
        )


def test_generic_codes_get_generic_text_not_a_random_specific_one(client):
    """`not_found` / `forbidden` 这类兜底码对应几十个场景。

    给它们一条**具体**消息（比如「Webhook 不存在」）是误导——
    生成这张表时我第一版就犯了这个错：取「同一码最长的那条消息」，
    结果所有 404 都变成了「Webhook 不存在」。
    """
    catalog = client_catalog()
    for code in GENERIC_CODES:
        assert code in catalog, f"{code} 不在文案表里"
        text = catalog[code]
        for specific in ("Webhook", "核验单", "合作体", "助理"):
            assert specific not in text, f"{code} 的文案太具体了：{text}"


# ---------------------------------------------------------- I18N-010 语言协商
def test_i18n010_unsupported_locales_fall_back_to_default():
    assert resolve_locale("fr-FR,fr;q=0.9") == DEFAULT_LOCALE
    assert resolve_locale("") == DEFAULT_LOCALE
    assert resolve_locale(None or "") == DEFAULT_LOCALE


def test_i18n010_traditional_chinese_falls_back_to_simplified_not_english():
    """这是一个**产品决定**：简繁差异不只是字形，但在没有繁体文案之前，
    回落到简体比回落到英文好。"""
    assert resolve_locale("zh-TW,zh-HK;q=0.9,en;q=0.8") == "zh-CN"


def test_i18n011_user_preference_wins_over_browser():
    """他明确选过的，不该被浏览器设置覆盖——很多人的浏览器语言
    并不是他想看的语言（公司统一装机、二手设备）。"""
    assert resolve_locale("en-US,en;q=0.9", "zh-CN") == "zh-CN"
    assert resolve_locale("zh-CN,zh;q=0.9", "en") == "en"


def test_i18n010_server_and_client_support_the_same_locales():
    src = I18N_TS.read_text(encoding="utf-8")
    m = re.search(r"export const SUPPORTED_LOCALES: Locale\[\] = \[(.*?)\];", src, re.S)
    assert m, "没找到 SUPPORTED_LOCALES"
    client_locales = set(re.findall(r"'([a-zA-Z-]+)'", m.group(1)))
    assert client_locales == set(SUPPORTED_LOCALES), (
        f"两端支持的语种不一致：服务端 {sorted(SUPPORTED_LOCALES)} / "
        f"客户端 {sorted(client_locales)}"
    )


# ------------------------------------------------- I18N-020 法律文本不进翻译表
def test_i18n020_legal_text_is_not_in_the_translation_table():
    """**机器翻译的合同条款是法律负债，不是国际化。**

    一份合同的效力取决于当事人对**那一份文本**的合意。把它交给 key-value
    翻译表，意味着有人改一行 JSON 就改了合同内容，而且没有任何审阅环节。

    正确做法是整份文本按语种单独维护、单独由律师审阅、单独版本化，
    并在合同里写明准据文本。这条测试是一个**故意不做**的闸门。
    """
    from app.modules.contract import clauses
    from app.modules.coop import compliance_path
    from app.modules.finance.compliance import CONTRACT_NATURE_CLAUSE

    catalog = client_catalog()
    joined = "\n".join(catalog.values())

    # 比的是**实际的法律文本常量**，不是「出现了法律词汇」。
    # 第一版我按关键词比（「著作权」等），结果误伤了一条错误消息——
    # 那句「按《著作权法》著作权默认归执行方」是在**解释为什么要选归属**，
    # 是提示不是条款。宽到误伤的闸门会被人关掉，等于没有闸门。
    legal_texts = [
        CONTRACT_NATURE_CLAUSE,
        clauses.CONFIDENTIALITY_CLAUSE,
        clauses.TEMPLATE_NOTICE,
        *(clauses.ip_clause(k) for k in clauses.IP_ASSIGNMENTS),
        *compliance_path.RISK_DISCLOSURE_POINTS,
    ]
    for text in legal_texts:
        # 取一段足够长的特征片段——整段比对太脆（改个标点就漏），
        # 太短又会误伤
        probe = text[:24]
        assert probe not in joined, (
            f"法律文本「{probe}…」进了翻译表——"
            f"合同条款必须整份按语种维护并经律师审阅，不能由 key-value 表拼装"
        )


def test_i18n020_legal_modules_still_hold_their_own_text():
    """反过来确认：法律文本仍然在它们自己的模块里，没有被搬走。"""
    from app.modules.contract import clauses
    from app.modules.coop import compliance_path

    assert "著作财产权" in clauses.ip_clause("assign")
    assert "保密" in clauses.CONFIDENTIALITY_CLAUSE
    assert any("稀释" in p for p in compliance_path.RISK_DISCLOSURE_POINTS)


# ------------------------------------------------------------ I18N-030 格式化
def test_i18n030_server_never_emits_localized_date_strings():
    """服务端只出 ISO-8601，展示交给客户端。

    这条现在已经是对的，写成测试是免得以后有人在服务端拼中文日期——
    那会让同一个接口在不同语种下返回不同的数据，而不是不同的展示。
    """
    offenders = []
    for p in (ROOT / "server" / "app").rglob("*.py"):
        src = p.read_text(encoding="utf-8")
        code = "\n".join(line.split("#")[0] for line in src.splitlines())
        if "strftime" in code and "%Y年" in code:
            offenders.append(str(p))
        if re.search(r'strftime\(["\'][^"\']*[一-龥]', code):
            offenders.append(str(p))
    assert not offenders, f"这些文件在服务端拼了本地化日期：{offenders}"


def test_i18n030_money_formatting_is_locale_aware_in_the_sdk():
    src = I18N_TS.read_text(encoding="utf-8")
    assert "export function formatMoney" in src
    # 整数分只在展示层格式化——浮点进业务逻辑是钱出错的经典途径
    assert "cents / 100" in src


def test_error_message_falls_back_to_server_text_not_to_the_code():
    """把 `insufficient_balance` 摆给用户看，和什么都不说差不多。

    这里断言的是 SDK 里那段兜底逻辑的**形状**（TS 运行时在 core 的
    vitest 里测；这条守的是「兜底顺序没被改掉」）。
    """
    src = I18N_TS.read_text(encoding="utf-8")
    body = src[src.index("export function errorMessage"):]
    assert "if (serverMessage) return serverMessage;" in body, "丢了「回落到服务端消息」这一档"
    assert "_SERVER_WORDED.has(code)" in body, "动态码没有优先用服务端消息"
