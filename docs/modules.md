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
├── io          I/O 工具 + 动态打印流
├── terminal    终端会话管理
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

## 终端管理 (terminal)

### 基本终端操作

```python
from echotools import LocalTerminal, SSHTerminal

# 本地终端
terminal = LocalTerminal()
await terminal.start()
await terminal.execute("ls -la")
output = await terminal.read()
await terminal.close()

# SSH终端
ssh = SSHTerminal(host="example.com", user="user")
await ssh.start()
await ssh.execute("command")
await ssh.close()
```

## I/O 工具 (io)

### 文件操作

```python
from echotools import atomic_write_text, ensure_directory, read_text_if_exists
from pathlib import Path

# 确保目录存在
ensure_directory(Path("/path/to/dir"))

# 原子���入文本
atomic_write_text(Path("/path/to/file.txt"), "content")

# 读取存在的文件
content = read_text_if_exists(Path("/path/to/file.txt"))
```

### 动态打印流 (printstream)

动态速度打印流系统，提供有序队列管理和自适应输出速度控制：

```python
from echotools import print_stream, configure_print_stream

# 配置打印速度
configure_print_stream(
    min_speed=5.0,    # 最小速度（字符/秒）
    max_speed=50.0,   # 最大速度（字符/秒）
    decay_factor=20.0, # 衰减因子
    smoothing_factor=0.8  # 平滑因子
)

# 使用动态打印���替代内置print��
print_stream("第一段文本：Hello World!")
print_stream("第二段文本：这是动态速度输出。")
print_stream("第三段文本��确保按顺序输出，不会交叉。")

# 批量输出
for i in range(5):
    print_stream(f"批量文本 {i+1}: " + "这是测试文本���" * 3)
```

### 打印流控制函数

```python
from echotools import (
    start_print_stream,
    stop_print_stream,
    flush_print_stream,
    get_buffer_size,
    get_queue_length,
    is_print_stream_running,
    set_print_speed,
)

# 手动控制
start_print_stream()
# ... 添加内容 ...
flush_print_stream()  # 立即输出所有内容
stop_print_stream()

# 监控状态
size = get_buffer_size()  # 获取缓冲区大小
length = get_queue_length()  # 获取队列长度
running = is_print_stream_running()  # 检查是否运行

# 动态调整速度
set_print_speed(min_speed=10.0, max_speed=100.0)
```

### PrintStream 类

```python
from echotools import PrintStream

# 创建自定义实例
stream = PrintStream(
    min_speed=5.0,
    max_speed=100.0,
    decay_factor=20.0,
    smoothing_factor=0.8
)

stream.start()
stream.add_to_buffer("自定义输出文本")
stream.flush_remaining()
stream.stop()
```