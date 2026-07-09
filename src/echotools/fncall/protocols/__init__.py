"""协议注册 — echotools 仅内置 entml 标记语言。"""

from echotools.protocol.base import register_protocol


def _register_all() -> None:
    from echotools.fncall.protocols.entml import EntmlProtocol

    register_protocol(EntmlProtocol())


_register_all()

__all__ = ["_register_all"]
