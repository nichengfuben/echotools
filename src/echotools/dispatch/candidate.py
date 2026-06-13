from __future__ import annotations

"""通用任务候选项。"""

import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ["TaskCandidate", "make_id"]


def make_id(group: str, resource_id: str = "") -> str:
    """生成候选项 ID。

    Args:
        group: 分组标识（如插件名）。
        resource_id: 资源标识，提供时生成确定性 ID。

    Returns:
        ID 字符串。
    """
    if resource_id:
        h = hashlib.sha256(
            "{}:{}".format(group, resource_id).encode()
        ).hexdigest()[:12]
        return "{}_{}".format(group, h)
    return "{}_{}".format(group, uuid.uuid4().hex[:12])


@dataclass
class TaskCandidate:
    """通用任务候选项。

    不预设任何 AI 语义，仅提供能力标记与可用性元数据。
    """

    id: str
    group: str
    resource_id: str = ""
    available: bool = True
    busy: bool = False
    cooldown: float = 0.0
    capabilities: Dict[str, bool] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    context_length: Optional[int] = None

    def has_capability(self, cap: str) -> bool:
        """检查是否具备指定能力。"""
        return bool(self.capabilities.get(cap, False))
