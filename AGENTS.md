# Agent 指南 — echotools

## 注释与文档分工

详细设计只写 `docs-src/`（若存在）或 `docs/`；**源码注释只解释当前实现里不易一眼看出的点**。

注释服务于读代码的人，不是凑合规字数。好注释回答 **「为何这样写」** 和 **「否则会怎样」**，不重复函数名/类型注解已表达的信息。

公开 API 的 docstring：**一句话职责即可**；参数/返回值能从类型注解读出时不逐条复述 `Args`/`Returns`/`Raises`。复杂逻辑用行内 `#` 放在分支或常量旁，不要堆在文件头。

---

## 禁止的注释套话（一律不得写入源码）

- 「标准模块」「项目标准模块」「作为 Provider-Evo 项目标准模块」
- 文件末尾「本模块对外契约」「相关模块」分隔注释块
- 「中文说明：」「公开方法/公开类 xxx。」等机械 docstring
- 「修改指引参见…」「保持单文件 200-400 行」等自描述套话
- 在 `.py` 里复述 `docs-src/`、`PROJECT_DECISIONS.md`、覆盖率门禁、`achecker` 规则等文档内容
- 为通过检查而堆砌的空洞 docstring 或 `# 模块导出` 式文件头

---

## 好注释（推荐模式）

保持简短，通常 1–3 行：

| 场景 | 写什么 |
|------|--------|
| **锁 / 并发** | 为何用 `threading.Lock` 而非 `asyncio.Lock`；多 event loop、跨线程调用；选错锁的后果 |
| **取消 / 超时** | 父协程 `CancelledError` 时须显式取消子任务，否则后台请求泄漏连接或使超时失效 |
| **魔法常量** | 阈值、窗口、burst 判定的业务后果；误触发或统计口径边界 |
| **兼容 / 降级** | 旧数据、可选 API、插件旧字段——退化行为是什么、为何不能更精确 |
| **跨层契约** | HTTP 状态码、错误码映射的前后端约定 |
| **信任边界** | 哪些字段可信、哪些用户可控；为何不用昵称/自由文本做安全判断 |
| **操作顺序** | 回滚、切换、清理时的步骤顺序，避免新旧状态混合 |

风格示例（非模板，勿照抄）：

```python
# SQLite WAL 仅单写；网关存在多 event loop / 跨线程直调，须用进程级 threading.Lock，
# asyncio.Lock 无法跨 loop 互斥。

# 调用方因 wait_for 取消时，必须 cancel 子任务并 await 清理，否则 httpx 请求仍在后台占用连接。
```

---

## 坏注释

- 重复函数名/参数名；上文「禁止套话」清单中的机械 docstring
- `@property` / getter 上仅复述属性名的 docstring（如 `"""配置中心。"""`）
- `"""初始化 xxx。"""` 且带 `Args:`，而签名与类型注解已完整
- 无实质信息的 `# ---- Public interface ----` 类内分隔块
- 在 `.py` 里复述架构长文、门禁规则、文档目录结构

---

## 与本仓库工具链

- **`achecker.py`**：目录子项、文件/函数行数、嵌套深度、语法等；**不**以 docstring 数量评分。注释整改不得靠堆字数过关。
- **`pytest --cov`**：覆盖率 omit 列表在 `pyproject.toml`；平台 capture 后端等 ctypes 代码可 omit，**不要在源码注释里解释 omit 原因**。
- 改注释后须本地通过：`pytest`、`python achecker.py`、`ruff check src`、`mypy src/echotools`。

---

## 发布（仅在被明确要求时）

版本号同步 `pyproject.toml`、`README.md`、`docs/CHANGELOG.md`；CI 全绿后再打 tag / PyPI。
