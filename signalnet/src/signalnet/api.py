"""节点 HTTP API（L3 层，REQ-NW-001）。标准库实现，JSON 进出。

GET  /head                    日志长度与 head
GET  /events?after=N          第 N 条之后的事件（gossip 同步用）
GET  /digest                  状态摘要
GET  /feed?now=&limit=&viewer=&algorithm=
GET  /content/<id>            内容 + 状态
GET  /jurors/<content_id>     当前轮抽中的陪审
POST /publish   {content, now}
POST /attest    {att, now}              （宽松模式）
POST /commit    {commit, now}
POST /reveal    {att, salt, now}
POST /settle    {content_id, now}       （宽松模式）
POST /record    {record, now}           关注/密钥/邀请/读者信号/申诉/治理/提现
POST /view      {record, now}           读者签名曝光回执
POST /tick      {now}

写请求串行执行；配置了 store 时每次写入后落盘。错误返回 400 {"error": ...}。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import attestation, content, records
from .node import SignalNode
from .store import SQLiteStore, event_to_dict


def _feed_item(f: Any) -> dict[str, Any]:
    return {
        "kind": f.kind,
        "content_id": f.content_id,
        "campaign_id": f.campaign_id,
        "label": f.label,
        "members": list(f.members),
    }


class NodeServer:
    def __init__(self, node: SignalNode, store: SQLiteStore | None = None) -> None:
        self.node = node
        self.store = store
        self.lock = threading.Lock()

    # ---- 路由 ----
    def get(self, path: str, q: dict[str, str]) -> Any:
        n = self.node
        if path == "/head":
            return {"len": len(n.ledger), "head": n.ledger.head}
        if path == "/events":
            after = int(q.get("after", 0))
            return [event_to_dict(e) for e in list(n.ledger)[after:]]
        if path == "/digest":
            return {"digest": n.state_digest()}
        if path == "/feed":
            items = n.feed(
                int(q.get("now", n.clock)),
                int(q.get("limit", 20)),
                q.get("viewer", ""),
                q.get("algorithm", ""),
            )
            return [_feed_item(f) for f in items]
        if path.startswith("/content/"):
            cid = path.rsplit("/", 1)[1]
            if cid not in n.contents:
                raise KeyError("内容不存在")
            st = n.state[cid]
            s = n.settlements.get(cid)
            return {
                "content": n.contents[cid].to_dict(),
                "level": st.level,
                "status": st.status,
                "klass": st.klass or st.prior_class,
                "consensus": s.consensus if s else None,
                "motif": n.motif_of(cid),
            }
        if path.startswith("/jurors/"):
            return list(n.jurors(path.rsplit("/", 1)[1]))
        raise KeyError(f"未知路径 {path}")

    def post(self, path: str, body: dict[str, Any]) -> Any:
        n = self.node
        now = body.get("now")
        with self.lock:
            if path == "/publish":
                out: Any = {"id": n.publish(content.Content.from_dict(body["content"]), now)}
            elif path == "/attest":
                n.attest(attestation.Attestation.from_dict(body["att"]), now)
                out = {"ok": True}
            elif path == "/commit":
                n.commit(attestation.Commit.from_dict(body["commit"]), now)
                out = {"ok": True}
            elif path == "/reveal":
                n.reveal(attestation.Attestation.from_dict(body["att"]), body["salt"], now)
                out = {"ok": True}
            elif path == "/settle":
                s = n.settle(body["content_id"], now)
                out = {"consensus": s.consensus}
            elif path == "/record":
                out = {"id": n.submit(records.Record.from_dict(body["record"]), now)}
            elif path == "/view":
                p = n.view_receipt(records.Record.from_dict(body["record"]), now)
                out = {"charged": p.charged if p else 0}
            elif path == "/tick":
                n.tick(int(now))
                out = {"ok": True}
            else:
                raise KeyError(f"未知路径 {path}")
            if self.store is not None:
                self.store.persist(n)
        return out

    # ---- HTTP ----
    def handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, obj: Any) -> None:
                data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                u = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                try:
                    self._send(200, server.get(u.path, q))
                except KeyError as e:
                    self._send(404, {"error": str(e)})
                except Exception as e:
                    self._send(400, {"error": str(e)})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                    self._send(200, server.post(urlparse(self.path).path, body))
                except KeyError as e:
                    self._send(404, {"error": str(e)})
                except Exception as e:
                    self._send(400, {"error": str(e)})

            def log_message(self, *args: Any) -> None:
                pass

        return Handler

    def serve(self, host: str = "127.0.0.1", port: int = 0) -> tuple[ThreadingHTTPServer, str]:
        httpd = ThreadingHTTPServer((host, port), self.handler())
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd, f"http://{host}:{httpd.server_address[1]}"
