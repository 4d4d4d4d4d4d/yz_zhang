"""SECEV-010 人机验证抽象（31 号 spec）。

之前 `docs/OPERATIONS.md` 写着「抽象位已留（SEC-021）」——**并没有留**，
全仓库没有一行 captcha 相关代码。这个文件是把那句话变成真的。

**验证码是给被误伤的人一条自证的路，不是多加一道墙。**
没有它时风控的唯一升级手段是封禁：一个手滑输错三次密码的真人，
和一个撞库脚本，得到的处置完全一样。
"""
import hashlib
from typing import Protocol


class CaptchaProvider(Protocol):
    name: str
    #  是否真的会拦人（直通实现为 False，用于面板诚实标注）
    enforcing: bool

    def verify(self, token: str, ip: str) -> bool: ...


class NoCaptcha:
    """直通实现：开发与测试默认。

    诚实命名：它**不验证任何东西**。叫 Default/Simple 会让人以为
    「至少有点用」，而它的作用是零。
    """

    name = "none"
    enforcing = False

    def verify(self, token: str, ip: str) -> bool:
        return True


class SandboxCaptcha:
    """形态真实的沙箱实现：token 必须是按 IP 派生的确定值。

    这样「要求验证码 → 校验 → 通过/拒绝」整条路径在测试里能真的跑通，
    而不是像直通实现那样永远返回 True——那种桩换供应商那天才第一次执行到
    失败分支，而那正是最不能出错的时刻（STUB-002 的教训）。
    """

    name = "sandbox"
    enforcing = True

    @staticmethod
    def expected(ip: str) -> str:
        return hashlib.sha256(f"sandbox-captcha:{ip}".encode()).hexdigest()[:12]

    def verify(self, token: str, ip: str) -> bool:
        return bool(token) and token == self.expected(ip)
