"""Further split console UI mixins."""
from __future__ import annotations

import re
from pathlib import Path

MIXINS = Path(__file__).resolve().parent / "src/echotools/media/console/uicore/mixins"


def _split_class_methods(path: Path, class_name: str, groups: dict[str, set[str]]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    header_end = next(i for i, l in enumerate(lines) if l.startswith(f"class {class_name}"))
    header = lines[: header_end + 1]
    body = lines[header_end + 1 :]

    methods: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(body):
        line = body[i]
        if line.startswith("    def ") or line.startswith("    async def "):
            m = re.search(r"def (\w+)", line)
            name = m.group(1) if m else ""
            chunk = [line]
            i += 1
            while i < len(body):
                nxt = body[i]
                if nxt.startswith("    def ") or nxt.startswith("    async def "):
                    break
                chunk.append(nxt)
                i += 1
            methods.append((name, chunk))
        else:
            i += 1

    grouped: dict[str, list[str]] = {k: [] for k in groups}
    for name, chunk in methods:
        placed = False
        for gname, names in groups.items():
            if name in names:
                grouped[gname].extend(chunk)
                placed = True
                break
        if not placed:
            raise RuntimeError(f"{path.name}: unassigned method {name}")

    base_header = header[0].split("\n")[0] if header else '"""Mixin."""'
    imports = path.read_text(encoding="utf-8").split(f"class {class_name}")[0]

    for gname, names in groups.items():
        cls = {
            "output": "_ConsoleUIOutputMixin",
            "stream": "_ConsoleUIStreamMixin",
            "interact": "_ConsoleUIInteractMixin",
            "cmds": "_ConsoleUICmdsMixin",
        }[gname]
        out_path = MIXINS / f"ui{gname}.py"
        out_path.write_text(imports + f"class {cls}:\n" + "".join(grouped[gname]), encoding="utf-8")
        print(out_path.name, len(out_path.read_text(encoding="utf-8").splitlines()))


_split_class_methods(
    MIXINS / "uioutput.py",
    "_ConsoleUIOutputMixin",
    {
        "output": {
            "print", "text", "color", "art", "box", "newline", "banner", "raw",
            "success", "warning", "error", "info", "debug", "divider", "panel",
            "table", "print_table", "kv_list", "columns", "tree",
        },
        "stream": {
            "stream", "stream_async", "stream_iter", "stream_aiter",
            "delete_lines", "clear_output", "clear_line", "clear_screen",
        },
    },
)

_split_class_methods(
    MIXINS / "uiinteract.py",
    "_ConsoleUIInteractMixin",
    {
        "interact": {
            "input_async", "input", "select", "confirm", "progress",
            "progress_async", "spinner", "timer", "multiline_input", "page",
            "countdown", "countdown_sync",
        },
        "cmds": {
            "register", "unregister", "execute", "show_commands", "header",
            "section", "bullet_list", "numbered_list", "quote", "badge",
            "pairs", "repl",
        },
    },
)
