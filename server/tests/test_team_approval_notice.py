"""TEAM-060~062 没有人被告知（67 号 spec）。

探针：员工提交一笔超额支出，老板驳回并写明理由——

    OWNER 收到的通知 : []
    DECIDE  : 200 {"id":1,"status":"rejected"}
    STAFF 收到的通知 : []

两端都是沉默的。最刺眼的是第二条：服务端**强制**要求写驳回理由
（`reason_required`），认真地把它存进 `decision_reason`，
**然后不送给任何人**——连 `decide` 的响应里都没有。

**「必须写」和「送到了」是两件事**（V89 的「必须选」和「看得见」同一条）。
"""
from app.core.db import SessionLocal
from app.modules.notification.models import Notification
from tests.conftest import auth
from tests.test_team_accounts import add_member, fund_team, make_team, make_user

REASON = "这批物料上月刚采购过，先用库存"


def notices(user_id: int, title: str | None = None) -> list[Notification]:
    with SessionLocal() as db:
        q = db.query(Notification).filter(Notification.user_id == user_id)
        if title:
            q = q.filter(Notification.title == title)
        return q.all()


def _team_with_staff(client, phones: tuple[str, str, str]):
    owner = make_user(client, phones[0], "老板")
    admin = make_user(client, phones[1], "主管")
    staff = make_user(client, phones[2], "员工")
    team_id = make_team(client, owner)
    fund_team(team_id, 500000)
    add_member(client, team_id, owner, admin, role="admin", limit=50000)
    add_member(client, team_id, owner, staff, role="member", limit=10000)
    return owner, admin, staff, team_id


def _request(client, team_id, who, cents=200000, purpose="采购一批物料"):
    r = client.post(f"/api/v1/teams/{team_id}/spends",
                    json={"amount_cents": cents, "purpose": purpose}, headers=auth(who))
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------- TEAM-060 审批人被告知
def test_team060_approvers_are_told_there_is_something_to_approve(client):
    """员工的活被卡住，而**卡住他的那个人从头到尾不知道**。"""
    owner, admin, staff, team_id = _team_with_staff(
        client, ("13300097001", "13300097002", "13300097003"))
    req = _request(client, team_id, staff)
    assert req["needed_approval"] is True

    for who in (owner, admin):
        got = notices(who["id"], "支出待审批")
        assert got, "审批人没被告知有东西等他批——这笔申请会一直躺着"
        # 正文要说清楚**谁、多少钱、干什么**，否则他还得自己去翻
        assert "员工" in got[-1].body and "¥2000.00" in got[-1].body
        assert "采购一批物料" in got[-1].body


def test_team060_requester_is_not_told_to_approve_his_own_request(client):
    """自己不能批自己（TEAM-021），所以给发起人发一条「等你审批」是纯噪音。

    要验的必须是**发起人本身就在审批人名单里**的那种情况——
    admin 超了自己的额度去申请。第一版拿 member 当发起人，
    而 member 根本不在 owner/admin 名单里：**红验时它不红，
    因为它压根没碰到那行排除逻辑。**
    """
    owner, admin, _staff, team_id = _team_with_staff(
        client, ("13300097010", "13300097011", "13300097012"))
    _request(client, team_id, admin, cents=80000)   # 超出 admin 的 ¥500 额度
    assert not notices(admin["id"], "支出待审批"), "给发起人发了一条「等你审批」"
    assert notices(owner["id"], "支出待审批"), "别的审批人应该照常收到"


def test_team060_in_limit_spend_notifies_nobody(client):
    """额度内自动批准的那条路上**没有人要做事**，不该打扰任何人。

    「有通知总比没有好」是错的：噪音会让真正要处理的那条被划过去。
    """
    owner, admin, staff, team_id = _team_with_staff(
        client, ("13300097020", "13300097021", "13300097022"))
    r = _request(client, team_id, staff, cents=5000, purpose="打印耗材")
    assert r["needed_approval"] is False
    for who in (owner, admin, staff):
        assert not notices(who["id"], "支出待审批")


# --------------------------------------------- TEAM-061 结果与理由送到发起人
def test_team061_rejection_notice_carries_the_reason_it_forced_you_to_write(client):
    """平台强制写理由，就得把它送到被驳回的人面前。

    理由的全部价值在于他读到它——据此决定是改金额、改用途，还是去谈。
    """
    owner, _admin, staff, team_id = _team_with_staff(
        client, ("13300097030", "13300097031", "13300097032"))
    req = _request(client, team_id, staff)
    d = client.post(f"/api/v1/teams/{team_id}/spends/{req['id']}/decide",
                    json={"approve": False, "reason": REASON}, headers=auth(owner))
    assert d.status_code == 200, d.text

    got = notices(staff["id"], "支出审批结果")
    assert got, "被驳回的人不知道自己被驳回了"
    assert REASON in got[-1].body, f"理由没送到：{got[-1].body}"


def test_team061_decide_response_returns_the_reason(client):
    """别逼界面再拉一次列表才能显示这段话。"""
    owner, _admin, staff, team_id = _team_with_staff(
        client, ("13300097040", "13300097041", "13300097042"))
    req = _request(client, team_id, staff)
    d = client.post(f"/api/v1/teams/{team_id}/spends/{req['id']}/decide",
                    json={"approve": False, "reason": REASON}, headers=auth(owner)).json()
    assert d["decision_reason"] == REASON


def test_team061_approval_notice_says_what_to_do_next(client):
    """批准了也要说——他不知道就不会去执行，钱一样停在原地。"""
    owner, _admin, staff, team_id = _team_with_staff(
        client, ("13300097050", "13300097051", "13300097052"))
    req = _request(client, team_id, staff)
    client.post(f"/api/v1/teams/{team_id}/spends/{req['id']}/decide",
                json={"approve": True, "reason": ""}, headers=auth(owner))
    body = notices(staff["id"], "支出审批结果")[-1].body
    assert "已获批准" in body and "执行" in body


# ------------------------------------------------- TEAM-062 **不**进必达表
def test_team062_approval_notices_are_not_must_reach(client):
    """V90 的判定标准是拿来做减法的，不是每次都用来做加法。

    审批通知不满足「错过就无法挽回」：申请不会因为没人看就作废，
    理由也一直躺在支出列表里可查。**把所有通知都做成不可关，
    用户会连真正重要的那几条一起屏蔽掉。**
    """
    from app.modules.notification.service import MUST_REACH

    for title in ("支出待审批", "支出审批结果"):
        assert ("team", title) not in MUST_REACH
