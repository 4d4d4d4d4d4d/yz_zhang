from datetime import timedelta
from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.coop.governance import PayoutProposal
from app.modules.coop.models import Distribution
from app.modules.wallet import service as wallet
from tests.conftest import auth
from tests.test_early_cooperation import make_user, make_venture, join, contribute, confirm


def setup(client):
    a=make_user(client,'13900880301','甲');b=make_user(client,'13900880302','乙')
    vid=make_venture(client,a,name='协作'*30);join(client,vid,b)
    cid=contribute(client,vid,a);confirm(client,vid,cid,b,10000)
    with SessionLocal() as db:
        wallet.topup(db,vid,30000);db.commit()
    base=f'/api/v1/ventures/{vid}'
    r=client.post(base+'/payout-proposals',headers=auth(a),json={'amount_cents':10000,'memo':'共同确认测试'})
    assert r.status_code==201,r.text
    return a,b,vid,base,r.json()


def execute(client,base,a,p,**over):
    return client.post(base+'/distributions',headers=auth(a),json={
        'amount_cents':p['amount_cents'],'memo':p['memo'],'proposal_id':p['id'],**over})


def vote(client,base,b,p,approve=True):
    return client.post(f'{base}/payout-proposals/{p["id"]}/vote',headers=auth(b),json={'approve':approve})


def test_payout_requires_unanimity_exact_parameters_and_executes_once(client):
    a,b,vid,base,p=setup(client)
    assert execute(client,base,a,p,proposal_id=None).status_code==403
    assert execute(client,base,a,p).status_code==403
    assert vote(client,base,b,p).status_code==200
    assert vote(client,base,b,p).json()['approvals'].__len__()==2
    assert execute(client,base,a,p,amount_cents=20000).status_code==409
    first=execute(client,base,a,p);assert first.status_code==201,first.text
    assert execute(client,base,a,p).json()==first.json()
    with SessionLocal() as db:
        assert db.query(Distribution).filter_by(venture_id=vid).count()==1
        assert wallet.get_or_create(db,vid).available_cents==20000


def test_payout_reject_expiry_and_outsider_access(client):
    a,b,vid,base,p=setup(client)
    other=make_user(client,'13900880303','外部人')
    assert client.get(base+'/payout-proposals',headers=auth(other)).status_code==403
    assert vote(client,base,other,p).status_code==403
    assert vote(client,base,b,p,False).json()['status']=='rejected'
    assert execute(client,base,a,p).status_code==409
    p=client.post(base+'/payout-proposals',headers=auth(a),json={'amount_cents':10000}).json()
    with SessionLocal() as db:
        db.get(PayoutProposal,p['id']).expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert vote(client,base,b,p).status_code==409
    assert execute(client,base,a,p).status_code==409


def test_payout_rejects_changed_contributions_or_members(client):
    a,b,vid,base,p=setup(client)
    assert vote(client,base,b,p).status_code==200
    cid=contribute(client,vid,b);confirm(client,vid,cid,a,10000)
    assert execute(client,base,a,p).status_code==409
    p=client.post(base+'/payout-proposals',headers=auth(a),json={'amount_cents':10000}).json()
    assert vote(client,base,b,p).status_code==200
    other=make_user(client,'13900880304','新成员');join(client,vid,other)
    assert execute(client,base,a,p).status_code==409
    with SessionLocal() as db:
        assert wallet.get_or_create(db,vid).available_cents==30000
