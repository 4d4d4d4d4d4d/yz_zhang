"""e签宝 SaaS API V3 transport. External signing is asynchronous, never HMAC-sign().

This adapter is NOT registered as a qualified SignatureProvider. Account onboarding,
provider acceptance testing and business-flow reconciliation remain required.
"""
import base64
import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlsplit

import httpx


class EsignError(RuntimeError):
    pass


def request_headers(app_id: str, secret: str, method: str, path: str, body: bytes, timestamp: int) -> dict:
    content_type = "application/json; charset=UTF-8"
    md5 = base64.b64encode(hashlib.md5(body).digest()).decode() if body else ""
    canonical = "\n".join([method.upper(), "*/*", md5, content_type, "", path])
    signature = base64.b64encode(hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).digest()).decode()
    return {"Accept": "*/*", "Content-Type": content_type, "Content-MD5": md5,
            "X-Tsign-Open-App-Id": app_id, "X-Tsign-Open-Auth-Mode": "Signature",
            "X-Tsign-Open-Ca-Timestamp": str(timestamp), "X-Tsign-Open-Ca-Signature": signature}


class EsignV3:
    def __init__(self, app_id: str, secret: str, *, sandbox: bool = True,
                 storage_hosts: tuple[str, ...] = (), transport=None):
        if not app_id or not secret:
            raise EsignError("电子签约账户尚未配置")
        self.app_id, self.secret = app_id, secret
        self.origin = "https://smlopenapi.esign.cn" if sandbox else "https://openapi.esign.cn"
        self.storage_hosts, self.transport = storage_hosts, transport

    def request(self, method: str, path: str, payload=None) -> dict:
        if not path.startswith('/v3/') or '?' in path or '#' in path or '..' in path:
            raise EsignError("Invalid API path")
        body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode() if payload is not None else b''
        headers = request_headers(self.app_id, self.secret, method, path, body, int(time.time() * 1000))
        try:
            with httpx.Client(timeout=20, follow_redirects=False, transport=self.transport) as client:
                response = client.request(method, self.origin + path, content=body, headers=headers)
                response.raise_for_status()
                value = response.json()
            if value.get('code') != 0 or (value.get('data') is not None and not isinstance(value.get('data'), dict)):
                raise EsignError("电子签约服务拒绝请求；请通过服务方后台核对状态")
            return value.get('data') or {}
        except (httpx.HTTPError, ValueError):
            # No automatic retries: a timed-out create may have succeeded remotely.
            # Avoid echoing account info, pre-signed URLs, provider body or credentials.
            raise EsignError("电子签约请求结果未确认，请核对服务方状态后再操作") from None

    @staticmethod
    def identifier(value: str) -> str:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
            raise EsignError("Invalid provider identifier")
        return value

    def upload_pdf(self, name: str, content: bytes) -> dict:
        if not content.startswith(b'%PDF-') or not 0 < len(content) <= 20 * 1024 * 1024:
            raise EsignError("必须提供 20 MB 以内的 PDF")
        if not re.fullmatch(r'[^/\\:*"<>|?\x00-\x1f]{1,95}\.pdf', name, re.IGNORECASE):
            raise EsignError("Invalid PDF filename")
        md5 = base64.b64encode(hashlib.md5(content).digest()).decode()
        upload = self.request('POST', '/v3/files/file-upload-url', {
            'contentMd5': md5, 'contentType': 'application/pdf', 'fileName': name,
            'fileSize': len(content), 'convertToPDF': False,
        })
        url = upload.get('fileUploadUrl', '')
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not parsed.hostname or parsed.hostname not in self.storage_hosts):
            raise EsignError("文件存储域名未列入明确允许列表")
        file_id = self.identifier(upload.get('fileId', ''))
        try:
            with httpx.Client(timeout=30, follow_redirects=False, transport=self.transport) as client:
                response = client.put(url, content=content, headers={'Content-Type': 'application/pdf', 'Content-MD5': md5})
                response.raise_for_status()
        except httpx.HTTPError:
            raise EsignError("文件上传结果未确认") from None
        return {'file_id': file_id, 'sha256': hashlib.sha256(content).hexdigest()}

    def create_draft(self, file_id: str, title: str, signers: list[dict]) -> dict:
        """Create reviewable draft only; never silently sends or auto-applies seals."""
        file_id = self.identifier(file_id)
        if not title or len(title) > 100 or not 2 <= len(signers) <= 10:
            raise EsignError("Invalid signing draft")
        parties = []
        for signer in signers:
            if not signer.get('account') or not signer.get('name'):
                raise EsignError("签署人账号和实名姓名均必填")
            parties.append({'signerType': 0,
                'psnSignerInfo': {'psnAccount': signer['account'], 'psnInfo': {'psnName': signer['name']}},
                'signConfig': {'forcedReadingTime': 10},
                'signFields': [{'fileId': file_id, 'mustSign': True,
                    'normalSignFieldConfig': {'freeMode': True, 'autoSign': False}}]})
        return self.request('POST', '/v3/sign-flow/create-by-file', {
            'docs': [{'fileId': file_id}],
            'signFlowConfig': {'signFlowTitle': title, 'autoStart': False, 'autoFinish': True},
            'signers': parties,
        })

    def start(self, flow_id: str) -> dict:
        return self.request('POST', f'/v3/sign-flow/{self.identifier(flow_id)}/start')

    def detail(self, flow_id: str) -> dict:
        return self.request('GET', f'/v3/sign-flow/{self.identifier(flow_id)}/detail')

    def signer_url(self, flow_id: str, account: str) -> str:
        data = self.request('POST', f'/v3/sign-flow/{self.identifier(flow_id)}/sign-url', {
            'clientType': 'ALL', 'needLogin': True, 'operator': {'psnAccount': account}, 'urlType': 2,
        })
        url = data.get('url', '')
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.username or parsed.password or not (parsed.hostname or '').endswith('.esign.cn'):
            raise EsignError("签署地址不在服务方域名内")
        return url
