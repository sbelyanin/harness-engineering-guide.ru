---
title: "Tool System"
section: core-concepts
author: Nexu
---

# Tool System

> **Главный инсайт:** Tools — это руки агента. Модель рассуждает; tools действуют. Но дизайн tool-системы — как tools регистрируются, описываются, диспетчеризуются и управляются — влияет на качество агента сильнее, чем сама модель.

## Что такое Tool?

Tool — это функция, которую модель может вызвать по имени со структурированными аргументами. Модель видит **схему** (имя, описание, типы параметров); harness берёт на себя **выполнение** (реальный вызов функции и возврат результата).

```python
# What the model sees (tool schema)
{
    "name": "read_file",
    "description": "Read the contents of a file at the given path",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to read"}
        },
        "required": ["path"]
    }
}

# What the harness executes (tool implementation)
def read_file(path: str) -> str:
    with open(path, 'r') as f:
        return f.read()
```

Модель никогда не видит и не выполняет реализацию. Она знает только схему. Это разделение фундаментально — значит, вы можете менять, как tool работает, не меняя поведение модели, и ограничивать, что делает tool, так, чтобы модель об этом не знала.

## Реестр Tools

Реестр tools (tool registry) — компонент harness, который связывает имена tools со схемами и реализациями:

```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, schema: dict, handler: Callable):
        self._tools[name] = Tool(name=name, schema=schema, handler=handler)

    def get_schemas(self) -> list[dict]:
        """Return schemas for the LLM API call."""
        return [t.schema for t in self._tools.values()]

    def dispatch(self, name: str, arguments: dict) -> str:
        """Execute a tool call and return the result as a string."""
        tool = self._tools.get(name)
        if not tool:
            return f"Error: Unknown tool '{name}'"
        try:
            result = tool.handler(**arguments)
            return str(result)
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
```

Заметьте, что `dispatch` всегда возвращает строку, даже при ошибках. Это намеренно — модель должна видеть сообщения об ошибках, чтобы адаптировать подход, а не падать молча.

## Статические vs. динамические Tools

**Статические tools** загружаются при старте и доступны всегда. Это работает для небольших наборов (5-15 tools), но ломается при масштабировании — 100 tools означают 100 схем в каждом API-вызове, что жрёт токены и путает модель.

**Динамические tools** (это ещё называют **skill loading**) решают проблему, показывая модели меню доступных категорий tools и подгружая конкретные tools только по запросу:

```python
# Instead of loading all 100 tools, show a menu
SKILL_MENU = """
Available skills (use load_skill to activate):
- file_ops: Read, write, search files
- git: Git operations (status, diff, commit, push)
- web: HTTP requests, web search
- database: SQL queries, schema inspection
"""

# The model calls load_skill("git") and then gets git-specific tools
def load_skill(skill_name: str) -> str:
    tools = skill_registry.load(skill_name)
    active_tools.extend(tools)
    return f"Loaded {len(tools)} tools: {[t.name for t in tools]}"
```

Экономия токенов драматична. Меню skill может стоить 200 токенов; загрузка всех tools upfront — 5 000+.

## Качество описания Tool

Способность модели правильно использовать tools почти полностью зависит от качества описаний. Расплывчатое описание ведёт к неправильному использованию; точное — направляет поведение:

```python
# Bad — the model will guess at behavior
{"name": "search", "description": "Search for things"}

# Good — unambiguous, includes format and constraints
{
    "name": "search_files",
    "description": "Search for files matching a glob pattern in the workspace. "
                   "Returns a list of relative file paths, one per line. "
                   "Max 100 results. Use '**/*.py' for recursive Python file search.",
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (e.g., '*.md', 'src/**/*.ts')"
            }
        },
        "required": ["pattern"]
    }
}
```

Ключевые принципы описания tools:
- Пишите, что tool **делает**, а не чем он **является**
- Указывайте **формат вывода** (JSON, plain text, по одному на строку)
- Включайте **ограничения** (максимум результатов, лимиты размера файла)
- Добавляйте **примеры** для неочевидных параметров

## Паттерны композиции Tools

Сложные возможности агента часто возникают из композиции простых tools, а не из построения сложных:

| Паттерн | Пример |
|---------|---------|
| **Sequential** | `read_file` → `edit_file` → `run_tests` |
| **Fan-out** | Прочитать 5 файлов параллельно, затем синтезировать |
| **Conditional** | `list_files` → решить, какие `read_file` |
| **Iterative** | `run_tests` → `edit_file` → `run_tests` (пока не пройдут) |

harness не обязан реализовывать эти паттерны — модель находит их сама через agentic loop. Ваша задача — дать правильные атомарные tools и позволить модели их компоновать.

## MCP: Model Context Protocol

[MCP](https://modelcontextprotocol.io/) — открытый стандарт для предоставления tools агентам поверх транспортного слоя (stdio, HTTP SSE). Вместо хардкода tools в harness, MCP позволяет подключаться к внешним tool-серверам:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"]
    }
  }
}
```

MCP важен тем, что отвязывает реализацию tool от harness. Tool, написанный для одного harness, работает в любом MCP-совместимом harness — Claude Desktop, OpenClaw, Cursor и других.

## Частые ошибки

- **Слишком много tools сразу** — больше ~20 активных tools ухудшает работу модели. Используйте динамическую загрузку.
- **Тихие падения** — tools, возвращающие пустую строку при ошибке, заставляют модель гадать. Всегда возвращайте явные сообщения об ошибках.
- **Пропущенные результаты tool** — если забыть добавить результат tool в историю сообщений, API-вызов упадёт. У каждого tool-вызова должен быть соответствующий результат.
- **Несогласованные типы возврата** — если `read_file` иногда возвращает контент, а иногда — dict с ошибкой, модель не сможет надёжно парсить вывод. Стандартизируйте формат результата.

## Что почитать

- [Anthropic: Tool Use Guide](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) — production-паттерны использования tools
- [Model Context Protocol](https://modelcontextprotocol.io/) — открытый стандарт для agent-tools
