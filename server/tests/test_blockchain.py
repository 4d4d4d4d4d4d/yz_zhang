import httpx
import pytest
from app.core.db import SessionLocal
from app.modules.anchor.blockchain import settings, status
from app.modules.anchor.service import anchor


def test_chain_unconfigured_is_not_verified(client, monkeypatch):
    monkeypatch.setattr(settings, 'CHAIN_RPC_URL', '')
    assert client.get('/api/v1/anchors/blockchain').json()['verified'] is False


@pytest.mark.parametrize('variant,expected', [('ok', 'confirmed'), ('digest', 'mismatch'), ('network', 'wrong_network'), ('rpc', 'unavailable')])
def test_checkpoints_require_confirmed_matching_chain(client, monkeypatch, variant, expected):
    monkeypatch.setattr(settings, 'CHAIN_RPC_URL', 'https://rpc.example.test')
    monkeypatch.setattr(settings, 'CHAIN_CONTRACT', '0x' + '1' * 40)
    monkeypatch.setattr(settings, 'CHAIN_ID', 31337)
    monkeypatch.setattr(settings, 'CHAIN_CONFIRMATIONS', 12)
    with SessionLocal() as db:
        entry = anchor(db, 'test', 'contract', 1, {'version': 1})
        def post(_self, _url, json):
            method = json['method']
            if variant == 'rpc':
                return httpx.Response(200, json={'error': {'code': -1}}, request=httpx.Request('POST', _url))
            results = {'eth_chainId': hex(1 if variant == 'network' else 31337), 'eth_blockNumber': hex(100), 'eth_getBlockByNumber': {'hash': '0x' + '2' * 64}}
            if method == 'eth_getBlockByNumber':
                assert json['params'][0] == hex(89)
            if method == 'eth_call':
                assert json['params'][1]['requireCanonical'] is True
                results[method] = hex(1) if json['params'][0]['data'] == '0x3bc684e9' else '0x' + format(1, '064x') + (entry.chain_hash if variant != 'digest' else 'f' * 64) + format(1234, '064x')
            return httpx.Response(200, json={'result': results[method]}, request=httpx.Request('POST', _url))
        monkeypatch.setattr(httpx.Client, 'post', post)
        result = status(db)
        assert result['status'] == expected
        assert result['verified'] == (expected == 'confirmed')


def test_external_coverage_does_not_skip_unbacked_gap(client):
    from app.modules.anchor.models import AnchorReceipt
    from app.modules.anchor.service import coverage
    with SessionLocal() as db:
        for i in range(3):
            anchor(db, 'test', 'contract', i, {'index': i})
        db.add(AnchorReceipt(seq_from=3, seq_to=3, chain_head='a' * 64, backed=True))
        db.flush()
        assert coverage(db)['third_party_backed_to_seq'] == 0
        assert coverage(db)['uncovered_entries'] == 3
