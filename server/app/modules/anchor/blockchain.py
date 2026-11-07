"""Read-only EVM checkpoint verification. Signing keys never enter the API process."""
import re

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from .models import AnchorEntry


def status(db: Session) -> dict:
    address = settings.CHAIN_CONTRACT
    if not settings.CHAIN_RPC_URL or not address:
        return {"status": "unconfigured", "verified": False,
                "note": "尚未接入外部链；平台哈希链不等于公网链存证。"}
    base = {"chain_id": settings.CHAIN_ID, "contract_address": address,
            "confirmations": settings.CHAIN_CONFIRMATIONS}
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address) or settings.CHAIN_CONFIRMATIONS < 1:
        return {**base, "status": "invalid_config", "verified": False}
    try:
        with httpx.Client(timeout=8, follow_redirects=False) as client:
            def rpc(method, params):
                response = client.post(settings.CHAIN_RPC_URL,
                                       json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                response.raise_for_status()
                value = response.json()
                if "error" in value or "result" not in value:
                    raise ValueError("RPC failed")
                return value["result"]

            if int(rpc("eth_chainId", []), 16) != settings.CHAIN_ID:
                return {**base, "status": "wrong_network", "verified": False}
            height = int(rpc("eth_blockNumber", []), 16)
            confirmed = max(0, height - settings.CHAIN_CONFIRMATIONS + 1)
            # Pin calls to a single confirmed block hash (EIP-1898), rejecting reorgs.
            block = rpc("eth_getBlockByNumber", [hex(confirmed), False])
            tag = {"blockHash": block["hash"], "requireCanonical": True}
            last = int(rpc("eth_call", [{"to": address, "data": "0x3bc684e9"}, tag]), 16)
            if not last:
                return {**base, "status": "pending", "verified": False}
            raw = rpc("eth_call", [{"to": address, "data": "0xb8a24252" + format(last, "064x")}, tag])
            if not re.fullmatch(r"0x[0-9a-fA-F]{192}", raw):
                raise ValueError("Invalid checkpoint")
            first, digest = int(raw[2:66], 16), raw[66:130].lower()
            entry = db.query(AnchorEntry).filter_by(seq=last).first()
            matches = bool(entry and entry.chain_hash == digest and 0 < first <= last)
            return {**base, "status": "confirmed" if matches else "mismatch", "verified": matches,
                    "seq_from": first, "seq_to": last, "digest": digest,
                    "block_number": confirmed, "block_hash": block["hash"],
                    "note": "链上记录证明摘要已发布，不自动证明业务事实或合同法律效力。"}
    except (httpx.HTTPError, ValueError, TypeError, KeyError, OverflowError):
        return {**base, "status": "unavailable", "verified": False}
