"""FIN-062 按期间的成交额与代扣税额（242 号 spec，V269）。

144 号的期间报表只有平台自己的收支（佣金、结算、补贴）。财务月结还要两组数：这个月平台上成交了多少
（按放款）、代扣了多少个税、缴库了多少、还有多少待缴。这两组数分开出表，口径逐条写明，标为草稿。
"""
from datetime import datetime

from app.core.db import SessionLocal
from app.modules.tax.models import TaxWithholding
from app.modules.tax.service import TAX_USER_ID
from app.modules.wallet import service as wallet
from app.modules.wallet.models import LedgerEntry
from tests.conftest import auth, make_admin
from tests.test_ticket_assign_reply import _admin

URL = "/api/v1/admin/platform-finance/gmv-tax"


def _seed():
    aug, sep = datetime(2026, 8, 15, 3), datetime(2026, 9, 10, 3)
    rows = [
        (201, "escrow_release", 9000, aug), (wallet.PLATFORM_USER_ID, "fee", 1000, aug),     # 一笔 100 元的单
        (202, "escrow_release", 4500, aug), (wallet.PLATFORM_USER_ID, "fee", 500, aug),      # 一笔 50 元的单
        (203, "escrow_release", 1800, datetime(2026, 8, 31, 16, 30)),                         # 北京时间 9 月 1 日 → 算 9 月
        (wallet.PLATFORM_USER_ID, "fee", 200, datetime(2026, 8, 31, 16, 30)),
        (204, "dispute_split", 3000, sep), (301, "refund", 7000, sep),
        (wallet.PLATFORM_USER_ID, "platform_settle", -800, sep),                              # 平台收支，不进本表
        (201, "tax_withheld", -600, aug), (TAX_USER_ID, "tax_withheld", 600, aug),
        (202, "tax_withheld", -300, aug), (TAX_USER_ID, "tax_withheld", 300, aug),
        (TAX_USER_ID, "tax_remit", -600, sep),
        (201, "topup", 99999, aug),                                                          # 充值不是成交
        (123, "fee", 99999, aug),                                                            # 别人账户上的 fee 不是平台佣金
    ]
    with SessionLocal() as db:
        db.add_all([LedgerEntry(user_id=u, kind=k, amount_cents=a, memo="t", created_at=t) for u, k, a, t in rows])
        db.add_all([TaxWithholding(user_id=201, contract_id=1, income_cents=9000, taxable_cents=9000, withheld_cents=600, created_at=aug),
                    TaxWithholding(user_id=202, contract_id=2, income_cents=4500, taxable_cents=4500, withheld_cents=300, created_at=aug),
                    TaxWithholding(user_id=201, contract_id=3, income_cents=1, taxable_cents=1, withheld_cents=0, created_at=aug)])
        db.commit()


def test_gmv_and_withholding_by_beijing_month(client):
    _seed()
    fin = make_admin(client, "13800342001", "财务")
    r = client.get(URL, params={"start": "2026-08", "end": "2026-09"}, headers=auth(fin))
    assert r.status_code == 200, r.text
    body = r.json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(body, "PlatformGmvTaxPeriods")
    _assert_shape(body["periods"][0], "PlatformGmvTaxRow")
    aug, sep = body["periods"]
    assert (aug["gmv_cents"], aug["release_count"], aug["executor_net_cents"], aug["fee_cents"]) == (15000, 2, 13500, 1500)
    assert (sep["gmv_cents"], sep["release_count"]) == (2000, 1), "北京时间 9 月 1 日 00:30 的放款算 9 月"
    assert (sep["dispute_split_cents"], sep["refund_cents"]) == (3000, 7000), "纠纷分账与退款另列、不进成交额"
    assert (aug["withheld_cents"], aug["withheld_count"], aug["withheld_people"], aug["withheld_income_cents"]) == (900, 2, 2, 13501)
    assert (aug["remitted_cents"], aug["tax_pending_cents"]) == (0, 900)
    assert (sep["withheld_cents"], sep["remitted_cents"], sep["tax_pending_cents"]) == (0, 600, 300), "期末待缴 = 专户到期末的余额"
    assert any("按放款" in b for b in body["basis"]) and "财税负责人确认" in body["draft_note"]
    q = client.get(URL, params={"granularity": "quarter", "start": "2026-08", "end": "2026-08"}, headers=auth(fin)).json()
    assert [(p["period"], p["gmv_cents"], p["withheld_cents"]) for p in q["periods"]] == [("2026-Q3", 17000, 900)]


def test_roles_and_range(client):
    fin = make_admin(client, "13800342011", "财务")
    ops = _admin(client, "13800342012", ["ops"])
    assert client.get(URL, headers=auth(ops)).status_code == 403
    assert client.get(URL, params={"start": "2026-05", "end": "2026-03"}, headers=auth(fin)).json()["detail"]["code"] == "period_range_invalid"
    d = client.get(URL, headers=auth(fin)).json()
    assert len(d["periods"]) == 12 and all(p["gmv_cents"] == 0 for p in d["periods"]), "默认最近 12 个月，没流水全是 0"
