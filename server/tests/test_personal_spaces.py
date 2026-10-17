from tests.conftest import auth
from app.core.db import SessionLocal
from app.modules.account.models import User


def payload(**extra):
    return dict(revision=0, published=True, headline='机器人与日常', introduction='一起造有趣的东西',
        theme='clay', items=[dict(title='我的作品', kind='work', summary='机械设计', url='https://example.com/work')], **extra)


def test_spaces_opt_in_publish_discover_and_retract(client, requester):
    uid = requester['id']
    assert client.get('/api/v1/spaces').json()['items'] == []
    own = client.get('/api/v1/spaces/me', headers=auth(requester)).json()
    assert own['published'] is False and own['revision'] == 0
    assert client.get(f'/api/v1/spaces/{uid}').status_code == 404
    saved = client.put('/api/v1/spaces/me', json=payload(), headers=auth(requester))
    assert saved.status_code == 200, saved.text
    public = client.get(f'/api/v1/spaces/{uid}')
    assert public.status_code == 200 and public.headers['cache-control'] == 'no-store'
    assert public.json()['items'][0]['title'] == '我的作品'
    assert not {'phone', 'real_name', 'lat', 'lng', 'id_masked', 'revision', 'privacy'} & set(public.json())
    assert len(client.get('/api/v1/spaces?q=机器人').json()['items']) == 1
    body = payload(); body.update(revision=1, published=False)
    assert client.put('/api/v1/spaces/me', json=body, headers=auth(requester)).status_code == 200
    assert client.get(f'/api/v1/spaces/{uid}').status_code == 404
    assert client.get('/api/v1/spaces').json()['items'] == []


def test_space_writes_require_owner_and_reject_stale_revision(client, requester, worker):
    assert client.put('/api/v1/spaces/me', json=payload()).status_code == 403
    assert client.put('/api/v1/spaces/me', json=payload(), headers=auth(requester)).status_code == 200
    assert client.put('/api/v1/spaces/me', json=payload(), headers=auth(requester)).status_code == 409
    assert client.get('/api/v1/spaces/me', headers=auth(worker)).json()['items'] == []
    assert client.put(f"/api/v1/spaces/{requester['id']}", json=payload(), headers=auth(worker)).status_code == 405


def test_space_privacy_ban_and_deletion_override_publication(client, requester):
    assert client.put('/api/v1/spaces/me', json=payload(), headers=auth(requester)).status_code == 200
    for attribute, value in [('privacy', {'profile_public': False}), ('is_banned', True), ('is_deleted', True)]:
        with SessionLocal() as db:
            u = db.get(User, requester['id']); setattr(u, attribute, value); db.commit()
        assert client.get('/api/v1/spaces').json()['items'] == []
        assert client.get(f"/api/v1/spaces/{requester['id']}").status_code == 404
        with SessionLocal() as db:
            u = db.get(User, requester['id']); setattr(u, attribute, {} if attribute == 'privacy' else False); db.commit()
    with SessionLocal() as db:
        db.get(User, requester['id']).privacy = {'profile_public': False}; db.commit()
    body = payload(); body['revision'] = 1
    assert client.put('/api/v1/spaces/me', json=body, headers=auth(requester)).status_code == 400


def test_space_external_links_and_limits(client, requester):
    for url in ['javascript:alert(1)', 'data:text/html,hello', '//example.com', 'http://example.com', 'https://a:b@example.com', 'https://example.com\\@evil.com', 'https://example.com/\n']:
        body = payload(); body['items'][0]['url'] = url
        assert client.put('/api/v1/spaces/me', json=body, headers=auth(requester)).status_code == 422
    body = payload(); body['items'] *= 25
    assert client.put('/api/v1/spaces/me', json=body, headers=auth(requester)).status_code == 422
    body = payload(); body['headline'] = ' '
    assert client.put('/api/v1/spaces/me', json=body, headers=auth(requester)).status_code == 400


def test_space_pagination_is_stable_and_search_escapes_wildcards(client, requester, worker):
    for user in [requester, worker]:
        assert client.put('/api/v1/spaces/me', json=payload(), headers=auth(user)).status_code == 200
    first = client.get('/api/v1/spaces?limit=1').json()
    second = client.get(f"/api/v1/spaces?limit=1&after={first['next_cursor']}").json()
    assert first['items'][0]['user_id'] != second['items'][0]['user_id']
    assert second['next_cursor'] is None
    assert client.get('/api/v1/spaces?q=%25').json()['items'] == []
    assert client.get('/api/v1/spaces?limit=1000').status_code == 422


def test_space_erased_with_account_and_included_in_owner_export(client, requester):
    from app.modules.account.deletion import erase_personal_data
    from app.modules.spaces.models import PersonalSpace
    client.put('/api/v1/spaces/me', json=payload(), headers=auth(requester))
    exported = client.get('/api/v1/users/me/export', headers=auth(requester)).json()
    assert exported['personal_space']['headline'] == '机器人与日常'
    with SessionLocal() as db:
        erase_personal_data(db, db.get(User, requester['id']))
        db.commit()
        assert db.get(PersonalSpace, requester['id']) is None
    assert client.get(f"/api/v1/spaces/{requester['id']}").status_code == 404


def test_space_shows_track_record_with_blind_review_rule(client, requester, worker):
    """SPACE-029 履约记录上门户（V140 演示：完成一单拿到五星，空间仍显示「慢慢生长」）。

    评价复用双盲揭晓规则：只有一方评过时不出现；双方都评完才出现；不带评价人。
    """
    from tests.conftest import topup
    from tests.test_client_shape_alignment import _assert_shape
    from tests.test_task_flow import match_and_fund, publish_task

    client.put('/api/v1/spaces/me', json=dict(payload(), headline='保洁八年'), headers=auth(worker))
    empty = client.get(f"/api/v1/spaces/{worker['id']}").json()['track_record']
    assert empty['tasks_completed'] == 0 and empty['recent_reviews'] == []
    topup(client, requester, 50000)
    task = publish_task(client, requester)
    match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    client.post(f"/api/v1/tasks/{task['id']}/reviews", json={'stars': 5, 'tags': ['细致'], 'comment': '很干净'},
                headers=auth(requester))
    blind = client.get(f"/api/v1/spaces/{worker['id']}").json()['track_record']
    assert blind['tasks_completed'] == 1 and blind['recent_reviews'] == []      # 对方还没评：盲窗内不出现
    client.post(f"/api/v1/tasks/{task['id']}/reviews", json={'stars': 5, 'comment': '付款及时'}, headers=auth(worker))
    rec = client.get(f"/api/v1/spaces/{worker['id']}").json()['track_record']
    _assert_shape(rec, 'SpaceTrackRecord')
    _assert_shape(rec['recent_reviews'][0], 'SpaceReview')
    assert rec['reviews_total'] == 1 and rec['top_tags'] == ['细致'] and rec['recent_reviews'][0]['comment'] == '很干净'
    assert 'reviewer_id' not in rec['recent_reviews'][0]
