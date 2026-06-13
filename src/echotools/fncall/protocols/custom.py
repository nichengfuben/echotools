from typing import Any, Dict, List, Optional, Tuple

from echotools.protocol.base import ToolProtocol

class CustomProtocol(ToolProtocol):
    """用户自定义 prompt 协议。

    不解析响应，依赖平台原生 tool_calls。
    仅注入用户提供的 prompt 模板。
    """

    def __init__(self, prompt_en: str = "", prompt_zh: str = ""):
        self._prompt_en = prompt_en
        self._prompt_zh = prompt_zh

    @property
    def id(self) -> str:
        return "custom"

    def get_trigger_tags(self) -> List[str]:
        return []

    def render_prompt(self, tool_descs, lang, user_system_prompt="", history_text="", loop_warning="", current_user_message=""):
        template = self._prompt_en if lang == "en" else self._prompt_zh
        if not template:
            return ""

        # Simple template substitution
        prompt = template
        prompt = prompt.replace("{tool_descs}", tool_descs)
        prompt = prompt.replace("{history_text}", history_text)
        prompt = prompt.replace("{loop_warning}", loop_warning)
        prompt = prompt.replace("{current_user_message}", current_user_message)
        prompt = prompt.replace("{user_system_prompt}", user_system_prompt)
        return prompt

    def detect_start(self, buffer: str) -> Tuple[bool, int]:
        return (False, -1)

    def parse(self, text, tools=None):
        return (text, [])

    def parse_fragment(self, fragment, tools=None):
        return []

    def clean_tags(self, content):
        return content.strip()

    def supports_streaming(self):
        return False
