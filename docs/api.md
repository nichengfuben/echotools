# API Reference

## EchoTools Facade

```python
from echotools import EchoTools

et = EchoTools(service_name="myapp", cache_cleanup_interval=60.0)
await et.startup()
# use et.config, et.logger, et.dispatcher, ...
await et.shutdown()
```

## Lazy Imports

Core symbols load on first access:

```python
import echotools
proto = echotools.get_protocol("xml")  # loads fncall lazily
```

## Coverage Targets

Core modules are measured in CI with `fail_under = 65%`.
Optional modules (`terminal`, heavy `fncall` parsers) are excluded from coverage gates.

See [modules.md](modules.md) for subsystem guides.
