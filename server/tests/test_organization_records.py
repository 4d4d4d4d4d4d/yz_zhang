from app.core.db import SessionLocal
from app.modules.coop.models import Contribution
from tests.conftest import auth
from tests.test_early_cooperation import make_user, make_venture, join


def body(owner,**over):
    return {'entity_type':'limited_company','jurisdiction':'CN / 上海','registered_name':'测试协作有限公司',
            'registration_number':'TEST-ONLY-NOT-REGISTERED','representative_user_id':owner['id'],
            'governance_basis':'以外部公司章程、股东名册和授权委托文件为准',
            'document_references':['公司章程：2026-10 草稿'],
            'rights':[{'holder_name':'测试股东','role':'shareholder','subscribed_cents':10000,
                      'paid_cents':5000,'interest_description':'外部文件记载的股份，不代表平台确权',
                      'source_document':'股东名册草稿第一项'}],
            'acknowledge_record_only':True,'acknowledge_member_visibility':True,**over}


def test_organization_records_versioned_and_do_not_mint_contribution_equity(client):
    owner=make_user(client,'13900880201','主体记录人');vid=make_venture(client,owner)
    url=f'/api/v1/ventures/{vid}/organization-records'
    first=client.post(url,headers=auth(owner),json=body(owner));assert first.status_code==201,first.text
    second=client.post(url,headers=auth(owner),json=body(owner,governance_basis='第二版外部协议及签约授权文件，等待核验'));assert second.status_code==201
    records=client.get(url,headers=auth(owner)).json()
    assert [r['revision'] for r in records]==[2,1]
    assert records[0]['record_hash']!=records[1]['record_hash']
    assert all(r['verification_status']=='declared_unverified' for r in records)
    with SessionLocal() as db:
        assert db.query(Contribution).filter_by(venture_id=vid).count()==0


def test_organization_records_member_access_and_explicit_visibility(client):
    owner=make_user(client,'13900880202','主体记录人');vid=make_venture(client,owner)
    other=make_user(client,'13900880203','未加入者');url=f'/api/v1/ventures/{vid}/organization-records'
    assert client.get(url,headers=auth(other)).status_code==403
    assert client.post(url,headers=auth(other),json=body(other)).status_code==403
    assert client.post(url,headers=auth(owner),json=body(owner,acknowledge_member_visibility=False)).status_code==422
    join(client,vid,other)
    assert client.post(url,headers=auth(owner),json=body(owner)).status_code==201
    assert len(client.get(url,headers=auth(other)).json())==1


def test_organization_role_and_capital_validation(client):
    owner=make_user(client,'13900880204','主体记录人');vid=make_venture(client,owner)
    url=f'/api/v1/ventures/{vid}/organization-records';data=body(owner)
    data['rights'][0]['role']='limited_partner'
    assert client.post(url,headers=auth(owner),json=data).status_code==400
    data=body(owner);data['rights'][0]['paid_cents']=10001
    assert client.post(url,headers=auth(owner),json=data).status_code==422
    assert client.post(url,headers=auth(owner),json=body(owner,registration_number='')).status_code==400
    assert client.post(url,headers=auth(owner),json=body(owner,representative_user_id=999999)).status_code==400
