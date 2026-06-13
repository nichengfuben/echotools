# echotools

通用基础设施 SDK：配置中心、日志、事件总线、调用链、任务调度、
插件框架、协议系统、自适应选择器，完全项目无关，兼容 Python 3.8-3.14。

## 安装

    pip install echotools[all]

## 快速开始

    from echotools import EchoTools

    et = EchoTools(service_name="myapp")
    et.logger.configure(level="INFO", color=True)
    cfg = et.config
    cfg.load("config.toml")

    with et.tracer.trace("request") as trace:
        with et.tracer.span(trace, "db") as span:
            span.set_tag("query", "select 1")

## 能力总览

- ConfigCenter      点路径配置 + 热重载 + 类型绑定
- LoggerManager     调用链注入 + 颜色 + 轮转
- EventBus          同步/异步事件
- Tracer            轻量调用链
- TaskDispatcher    单发/竞速 + 自适应选择
- PluginRegistry    自动发现 + 热重载
- get_protocol      XML/antml/original/bracket/nous/custom 协议
- ProxyManager      HTTP/HTTPS/SOCKS
- AutoUpdater       git 自动更新
- FileWatcher       轮询文件监视
