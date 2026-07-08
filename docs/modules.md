# echotools 模块指南

## 架构概览

```
EchoTools (facade)
├── config      配置中心 + 热重载
├── logger      日志与颜色
├── events      事件总线
├── tracer      调用链
├── dispatcher  任务竞速 + 贝叶斯选择
├── plugins     插件发现与生命周期
├── proxy       HTTP/SOCKS 代理
└── web         aiohttp 应用（可选）
```

## 配置 (config)

```python
from echotools import ConfigCenter

cfg = ConfigCenter()
cfg.load("config.toml")
port = cfg.get("server.port", 8080)
```

## 任务调度 (dispatch)

```python
from echotools import TaskCandidate, TaskDispatcher

async def executor(cand):
    yield "chunk"

dispatcher = TaskDispatcher()
async for chunk in dispatcher.dispatch(
    [TaskCandidate(id="a", group="g")],
    executor,
    concurrent=2,
    min_tokens=5,
):
    print(chunk)
```

## LLM 工具协议 (fncall)

```python
from echotools import get_protocol, inject_fncall

proto = get_protocol("xml")
messages = inject_fncall([{"role": "user", "content": "hi"}], tools, proto)
```

## Web（需要 `pip install echotools[http]`）

```python
from echotools import WebApplication

app = WebApplication()
app.add_route("GET", "/health", health_handler)
```

## 可选依赖

| Extra | 用途 |
|-------|------|
| `toml` | TOML 配置 |
| `http` | aiohttp Web |
| `ssh` | SSH 终端 |
| `all` | 全部功能 |
