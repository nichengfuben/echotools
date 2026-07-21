from __future__ import annotations

"""文件工具集。"""

import base64
import hashlib
import mimetypes
import os
import re
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from echotools.base.logger.manager import get_logger

__all__ = ["FileUtil"]

logger = get_logger(__name__)

_URI_RE = re.compile(
    r"^data:(?P<mime>[\w/+.\-]+)(?:;[^,]*)?(?P<data>,.+)$", re.DOTALL
)
_EXT: Dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".json": "application/json",
    ".py": "text/x-python",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


class FileUtil:
    """文件工具集——静态方法集合。"""

    @staticmethod
    def mime(name: str) -> str:
        """推断 MIME 类型。"""
        ext = os.path.splitext(name)[1].lower()
        return (
            _EXT.get(ext)
            or mimetypes.guess_type(name)[0]
            or "application/octet-stream"
        )

    @staticmethod
    def is_url(p: str) -> bool:
        """判断是否为 HTTP/HTTPS URL。"""
        return p.startswith(("http://", "https://"))

    @staticmethod
    def is_data_uri(d: str) -> bool:
        """判断是否为 Data URI。"""
        return (
            isinstance(d, str)
            and d.startswith("data:")
            and ";base64," in d
        )

    @staticmethod
    def parse_data_uri(uri: str) -> Optional[Tuple[str, bytes]]:
        """解析 Data URI，返回 (mime, bytes)。"""
        if not FileUtil.is_data_uri(uri):
            return None
        try:
            m = _URI_RE.match(uri)
            if not m:
                return None
            b64 = (
                m.group("data")
                .strip()
                .replace("\n", "")
                .replace("\r", "")
                .replace(" ", "")
            )
            if b64.startswith(","):
                b64 = b64[1:]
            pad = 4 - len(b64) % 4
            if pad != 4:
                b64 += "=" * pad
            return m.group("mime"), base64.b64decode(b64)
        except Exception:
            return None

    @staticmethod
    def save_data_uri(
        uri: str, directory: str = "data/uploads"
    ) -> Optional[str]:
        """保存 Data URI 到本地。"""
        r = FileUtil.parse_data_uri(uri)
        if not r:
            return None
        mime_type, data = r
        Path(directory).mkdir(parents=True, exist_ok=True)
        ext_map: Dict[str, str] = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "application/pdf": ".pdf",
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
            "video/mp4": ".mp4",
        }
        ext = ext_map.get(mime_type, ".bin")
        fp = Path(directory) / "{}_{}{}".format(
            int(time.time() * 1000), uuid.uuid4().hex[:8], ext
        )
        fp.write_bytes(data)
        return str(fp)

    @staticmethod
    def cleanup(path: str) -> None:
        """删除临时文件（忽略错误）。"""
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.debug("清理临时文件 %s 失败: %s", path, e)

    @staticmethod
    def md5(path: str) -> str:
        """计算文件 MD5。"""
        h = hashlib.md5()  # noqa: S324
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def read_chunks(path: str, chunk_size: int = 8192) -> List[bytes]:
        """按块读取文件。"""
        chunks: List[bytes] = []
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                chunks.append(chunk)
        return chunks

    @staticmethod
    def ensure_dir(path: str) -> str:
        """确保目录存在。"""
        Path(path).mkdir(parents=True, exist_ok=True)
        return path
