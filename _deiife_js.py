from pathlib import Path


def de_iife(path: Path, start: str, end: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        if start in line:
            out.append("'use strict';")
            continue
        if end in line:
            continue
        if line.startswith("  "):
            out.append(line[2:])
        else:
            out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


root = Path("src/echotools/media/web/input_box")
de_iife(root / "inputbox.js", "(function()", "})();")
de_iife(root / "components/textinput.js", "(() => {", "})();")
de_iife(root / "components/sortablelist.js", "(function(global)", "})(window);")
