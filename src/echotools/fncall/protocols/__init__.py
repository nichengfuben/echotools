"""协议注册。

导入时自动注册所有内置协议。
"""

from echotools.protocol.base import register_protocol


def _register_all() -> None:
    """注册所有内置协议。"""
    from echotools.fncall.protocols.antml import AntmlProtocol
    from echotools.fncall.protocols.bracket import BracketProtocol
    from echotools.fncall.protocols.dsml import DsmlProtocol
    from echotools.fncall.protocols.nous import NousProtocol
    from echotools.fncall.protocols.original import OriginalProtocol
    from echotools.fncall.protocols.xml import XmlProtocol

    register_protocol(XmlProtocol())
    register_protocol(AntmlProtocol())
    register_protocol(OriginalProtocol())
    register_protocol(BracketProtocol())
    register_protocol(NousProtocol())
    register_protocol(DsmlProtocol())
    # custom 协议按需创建，不在此注册


# 模块导入时自动注册
_register_all()

__all__ = ["_register_all"]
