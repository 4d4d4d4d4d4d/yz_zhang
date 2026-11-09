"""SignalNet：以 Proof of Signal（声誉质押）衡量信息质量的去中心化内容社区。

分层（由 harness/gate.py 的分层门禁强制）：
    L0  crypto, ledger                       —— 原语
    L1  content, attestation                 —— 签名数据对象
    L2  reputation, ranking, ads, federation —— 机制
    L3  node, cli                            —— 组装与入口
"""

__version__ = "0.1.0"
