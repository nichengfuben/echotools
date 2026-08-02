# echotools

通用基础设施 SDK：配置、日志、事件、调度、插件、调用链，以及 **entml** LLM 工具调用协议与终端 Console UI。

完全项目无关，兼容 Python 3.8–3.14。当前版本：**2.4.3**（详见 [CHANGELOG](docs/CHANGELOG.md)）。

## 安装

```bash
# 核心（仅 typing-extensions）
pip install echotools

# 完整功能（含 TOML、Web、终端、Console UI 等）
pip install echotools[all]
```

### 可选依赖

| Extra | 用途 |
|-------|------|
| `toml` | TOML 配置读写 |
| `watch` | watchdog 文件监视 |
| `http` | aiohttp Web 层 |
| `socks` | SOCKS 代理 |
| `ssh` | SSH 终端 |
| `terminal` | Windows ConPTY |
| `console` | Rich 终端 UI（渐变、表格、交互选择） |
| `all` | 全部可选依赖 |
| `dev` | pytest、ruff、mypy |

## 快速开始

### 基础设施

```python
from echotools import EchoTools

et = EchoTools(service_name="myapp")
et.logger.configure(level="INFO", color=True)
cfg = et.config
cfg.load("config.toml")

with et.tracer.trace("request") as trace:
    with et.tracer.span(trace, "db") as span:
        span.set_tag("query", "select 1")

await et.shutdown()
```

### entml 工具调用

内置 **entml**（`<entml:*>` 熵标记语言）协议，负责 prompt 注入与模型输出解析。

```python
from echotools import FncallStreamParser, get_protocol, inject_fncall

tools = [
    {
        "name": "Bash",
        "description": "Run a shell command",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    }
]
messages = [{"role": "user", "content": "列出当前目录"}]

proto = get_protocol()
out_messages = inject_fncall(messages, tools, proto, lang="zh")

parser = FncallStreamParser(proto, tools=tools)
for chunk in model_stream:
    parser.feed(chunk)
    if parser.get_ready_tool_calls():
        ...
result = parser.finalize()
```

能力包括：prompt 注入（history / 工具结果 / thinking 模式）、batch `parse()`、流式
`partial_text` / `input_json_delta`、伪 history 剥离、工具循环检测。

### 终端 Console UI

需要 `pip install echotools[console]`（或 `[all]`）：

```python
from echotools.media.console import (
    create_themed_ui,
    render_gradient_banner,
    render_text_lines,
    run_select,
)

ui = create_themed_ui(theme_name="ocean")  # ocean / forest / sunset / violet / rose / slate / cyan
print(render_gradient_banner(render_text_lines("echotools"), theme_name="ocean"))
choice = run_select(ui, "选择主题", ["ocean", "forest", "sunset"])
```

## 能力总览

| 模块 | 说明 |
|------|------|
| `EchoTools` | 门面：配置、日志、事件、调度、插件等统一入口 |
| `ConfigCenter` | 点路径配置 + 热重载 + 类型绑定 |
| `LoggerManager` | 调用链注入 + 颜色 + 轮转 |
| `EventBus` | 同步/异步事件 |
| `Tracer` | 轻量调用链 |
| `TaskDispatcher` | 单发/竞速 + 贝叶斯自适应选择 |
| `PluginRegistry` | 自动发现 + 热重载 |
| `get_protocol` / `inject_fncall` | entml 工具协议与 prompt 注入 |
| `FncallStreamParser` | 流式工具调用解析 |
| `media.console` | Rich 终端 UI、多主题、交互选择与 ANSI 渐变 |
| `PrintStream` | 动态速度打印流 |
| `ProxyManager` | HTTP/HTTPS/SOCKS |
| `WebApplication` | aiohttp Web（需 `[http]`） |
| `LocalTerminal` / `SSHTerminal` | 终端会话（需 `[terminal]` / `[ssh]`） |
| `AutoUpdater` | git 自动更新 |
| `FileWatcher` | 轮询文件监视 |

## 开发

```bash
pip install -e ".[dev,all]"
make -C docs lint
make -C docs test
make -C docs cov
```

模块指南见 [docs/modules.md](docs/modules.md)，API 参考见 [docs/api.md](docs/api.md)。

## 变更记录

见 [docs/CHANGELOG.md](docs/CHANGELOG.md)。

## 许可证

MIT
