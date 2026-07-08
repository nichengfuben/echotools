# echotools

通用基础设施 SDK：配置中心、日志、事件总线、调用链、任务调度、
插件框架、协议系统、自适应选择器，完全项目无关，兼容 Python 3.8–3.14。

## 安装

```bash
# 核心（仅 typing-extensions）
pip install echotools

# 完整功能
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
| `all` | 全部可选依赖 |
| `dev` | pytest, ruff, mypy |

## 快速开始

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

## 能力总览

| 模块 | 说明 |
|------|------|
| `ConfigCenter` | 点路径配置 + 热重载 + 类型绑定 |
| `LoggerManager` | 调用链注入 + 颜色 + 轮转 |
| `EventBus` | 同步/异步事件 |
| `Tracer` | 轻量调用链 |
| `TaskDispatcher` | 单发/竞速 + 贝叶斯自适应选择 |
| `PluginRegistry` | 自动发现 + 热重载 |
| `get_protocol` | XML/antml/original/bracket/nous 等 LLM 工具协议 |
| `ProxyManager` | HTTP/HTTPS/SOCKS |
| `AutoUpdater` | git 自动更新 |
| `FileWatcher` | 轮询文件监视 |

## 开发

```bash
pip install -e ".[dev,all]"
make lint
make test
make cov
```

模块指南见 [docs/modules.md](docs/modules.md)，API 参考见 [docs/api.md](docs/api.md)。

## 许可证

MIT
