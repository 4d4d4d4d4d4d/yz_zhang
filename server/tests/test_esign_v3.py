import base64
import hashlib
import hmac
import json
import httpx
import pytest
from app.vendors.esign_v3 import EsignV3, EsignError, request_headers


def test_request_auth_binds_exact_utf8_body():
    body = '{"name":"张三"}'.encode()
    result = request_headers('app', 'secret', 'POST', '/v3/test', body, 1700000000000)
    md5 = base64.b64encode(hashlib.md5(body).digest()).decode()
    canonical = f'POST\n*/*\n{md5}\napplication/json; charset=UTF-8\n\n/v3/test'
    assert result['X-Tsign-Open-Ca-Signature'] == base64.b64encode(hmac.new(b'secret', canonical.encode(), hashlib.sha256).digest()).decode()
    assert result['X-Tsign-Open-Ca-Timestamp'] == '1700000000000'


def test_upload_rejects_unapproved_host_before_sending_document():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'code': 0, 'data': {'fileId': 'file1', 'fileUploadUrl': 'https://127.0.0.1/private'}})
    api = EsignV3('app', 'secret', transport=httpx.MockTransport(handler))
    with pytest.raises(EsignError):
        api.upload_pdf('contract.pdf', b'%PDF-1.7 test')
    assert len(calls) == 1


def test_draft_requires_human_review_and_signing():
    def handler(request):
        body = json.loads(request.content)
        assert body['signFlowConfig']['autoStart'] is False
        assert all(s['signFields'][0]['normalSignFieldConfig']['autoSign'] is False for s in body['signers'])
        assert request.url.host == 'smlopenapi.esign.cn'
        return httpx.Response(200, json={'code': 0, 'data': {'signFlowId': 'flow1'}})
    api = EsignV3('app', 'secret', transport=httpx.MockTransport(handler))
    assert api.create_draft('file1', 'Review', [{'account': '13800000001', 'name': 'A'}, {'account': '13800000002', 'name': 'B'}])['signFlowId'] == 'flow1'


def test_unknown_create_result_not_retried_or_leaked():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('private provider payload', request=request)
    api = EsignV3('app', 'secret', transport=httpx.MockTransport(handler))
    with pytest.raises(EsignError) as error:
        api.start('flow1')
    assert 'private' not in str(error.value)
    assert len(calls) == 1
