---
author: Nexu
---

# Skill System

> **Главный инсайт:** Skill — это не tool, а *бандл* связанных tools, документации и правил поведения, упакованных в одну возможность. Skill-система превращает «100 tools, запиханных в каждый промпт» в «меню возможностей, подгружаемых по требованию», экономя тысячи токенов и резко повышая точность выбора tools.

## Что такое Skill?

Tool — это одна функция, которую может вызвать модель. **Skill** — упакованная возможность, объединяющая:

- **Tools** — одну или несколько связанных схем функций и обработчиков
- **Документацию** — файл SKILL.md, объясняющий, когда и как использовать skill
- **Правила поведения** — ограничения, паттерны и конвенции для модели

```
skill/
├── SKILL.md          # Документация: когда использовать, как, ограничения
├── tools.py          # Реализации tools
└── schema.json       # Схемы tools (или генерируются из кода)
```

Например, skill `git` не выставляет один tool `git` — он бандлит `git_status`, `git_diff`, `git_commit`, `git_push`, `git_log` и включает документацию по конвенциям commit-сообщений, именованию веток и тому, когда спрашивать перед push.

## Skill vs. Tool

| | Tool | Skill |
|---|------|-------|
| **Область** | Одна функция | Бандл связанных функций |
| **Документация** | Описание параметров | Полный SKILL.md с примерами, конвенциями |
| **Загрузка** | Всегда есть или отсутствует | По требованию из меню |
| **Стоимость в context** | ~100–200 токенов на схему | ~200 токенов пункт меню + ~1 000 токенов при загрузке |
| **Правила поведения** | Нет | Могут включать ограничения, workflow, паттерны |

Различие важно для токен-экономики. harness со 100 tools платит ~12 000 токенов за API-вызов только на схемы. Skill-система с 15 skills и меню на 300 токенов грузит только нужное.

## Формат SKILL.md

Файл SKILL.md — инструкция к skill. Модель читает его при загрузке skill:

```markdown
# Git Operations

## When to Use
- User asks to check, commit, or push code changes
- You need to inspect file history or diffs
- Resolving merge conflicts

## Available Tools
- `git_status` — Show working tree status
- `git_diff` — Show changes (staged or unstaged)
- `git_commit` — Commit staged changes with a message
- `git_push` — Push commits to remote
- `git_log` — Show recent commit history

## Conventions
- Always run `git_status` before committing
- Use conventional commit messages (feat:, fix:, docs:)
- Never force-push without explicit user approval
- Commit message should be under 72 characters

## Examples
To commit and push:
1. `git_status` → review what's changed
2. `git_diff` → verify the changes are correct
3. `git_commit("feat: add user auth middleware")`
4. `git_push`
```

Этот формат даёт модели достаточно context, чтобы правильно использовать skill, не встраивая все эти знания в описания tools.

## Паттерн Skill-меню

Вместо загрузки всех tools при старте покажите модели компактное меню доступных skills. Модель читает меню, решает, какой skill нужен, и грузит его:

```python
SKILL_MENU = """Available skills (use load_skill to activate):

- file_ops: Read, write, search, and edit files in the workspace
- git: Version control — status, diff, commit, push, log
- web: HTTP requests, web search, URL fetching
- shell: Execute shell commands in a sandbox
- database: SQL queries, schema inspection, migrations
- calendar: Create events, check availability, manage schedules
- email: Read inbox, send emails, search messages
- image: Generate and analyze images
"""
```

Меню стоит ~150 токенов. Загрузка skill добавляет его SKILL.md (~500–1 000 токенов) и схемы tools (~200–800 токенов). В сравнении с загрузкой всех tools upfront:

```
Стратегия                      Токены (8 skills, ~60 tools)
────────────────────────────────────────────────────────
Все tools upfront:             ~12 000 токенов (всегда)
Меню + 2 загруженных skill:    ~150 + ~2 400 = ~2 550 токенов
────────────────────────────────────────────────────────
Экономия:                      ~9 450 токенов за ход (78%)
```

За сессию из 30 ходов это ~280K сэкономленных токенов — реальные деньги по API-тарифам.

## Реализация реестра Skills

```python
import json
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class Skill:
    name: str
    description: str
    doc: str                           # Contents of SKILL.md
    tools: list[dict] = field(default_factory=list)        # Tool schemas
    handlers: dict = field(default_factory=dict)            # name → callable

class SkillRegistry:
    """Registry with on-demand skill loading."""

    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
        self._catalog: dict[str, Skill] = {}
        self._active: dict[str, Skill] = {}
        self._scan()

    def _scan(self):
        """Scan the skills directory and build the catalog."""
        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            schema_file = skill_dir / "schema.json"
            if not skill_md.exists():
                continue

            doc = skill_md.read_text()
            # Extract first line after "# " as description
            first_heading = ""
            for line in doc.splitlines():
                if line.startswith("# "):
                    first_heading = line[2:].strip()
                    break

            schemas = []
            if schema_file.exists():
                schemas = json.loads(schema_file.read_text())

            self._catalog[skill_dir.name] = Skill(
                name=skill_dir.name,
                description=first_heading,
                doc=doc,
                tools=schemas,
            )

    def get_menu(self) -> str:
        """Generate the skill menu for the model."""
        lines = ["Available skills (use load_skill to activate):\n"]
        for name, skill in self._catalog.items():
            status = " [loaded]" if name in self._active else ""
            lines.append(f"- {name}: {skill.description}{status}")
        return "\n".join(lines)

    def load_skill(self, name: str) -> str:
        """Load a skill, making its tools available."""
        if name not in self._catalog:
            return f"Error: Unknown skill '{name}'. Check the skill menu."
        if name in self._active:
            return f"Skill '{name}' is already loaded."

        skill = self._catalog[name]
        self._active[name] = skill
        tool_names = [t["name"] for t in skill.tools]
        return (
            f"Loaded skill '{name}' with {len(skill.tools)} tools: "
            f"{', '.join(tool_names)}\n\n"
            f"Documentation:\n{skill.doc}"
        )

    def unload_skill(self, name: str) -> str:
        """Unload a skill to free up context space."""
        if name not in self._active:
            return f"Skill '{name}' is not loaded."
        del self._active[name]
        return f"Unloaded skill '{name}'."

    def get_active_schemas(self) -> list[dict]:
        """Return tool schemas for all currently loaded skills."""
        schemas = []
        for skill in self._active.values():
            schemas.extend(skill.tools)
        # Always include the meta-tools
        schemas.append({
            "name": "load_skill",
            "description": "Load a skill by name to activate its tools",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name from the menu"}
                },
                "required": ["name"],
            },
        })
        return schemas

    def dispatch(self, tool_name: str, arguments: dict) -> str:
        """Dispatch a tool call to the appropriate skill handler."""
        if tool_name == "load_skill":
            return self.load_skill(arguments["name"])

        for skill in self._active.values():
            if tool_name in skill.handlers:
                try:
                    return str(skill.handlers[tool_name](**arguments))
                except Exception as e:
                    return f"Error: {type(e).__name__}: {e}"

        return f"Error: Tool '{tool_name}' not found. Is the skill loaded?"
```

## Тонкий Harness + толстые Skills

Архитектурный принцип: harness должен быть тонким — только agentic loop, сборка context и реестр skills. Вся доменная специфика живёт в skills:

```
┌─────────────────────────────────────────────────┐
│  Harness (тонкий)                                │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ Agentic  │  │  Context   │  │    Skill     │ │
│  │  Loop    │  │ Assembler  │  │  Registry    │ │
│  └──────────┘  └───────────┘  └──────────────┘ │
└─────────────────────┬───────────────────────────┘
                      │ грузит по требованию
     ┌────────────────┼────────────────┐
     ▼                ▼                ▼
┌─────────┐    ┌───────────┐    ┌───────────┐
│  git    │    │  file_ops  │    │  web      │
│  skill  │    │  skill     │    │  skill    │
└─────────┘    └───────────┘    └───────────┘
```

У этого разделения практические плюсы:
- **Skills портируемы** — skill, написанный для одного harness, работает в другом
- **Skills тестируемы** — tools и схемы можно тестировать изолированно
- **Skills компонуются** — модель сама находит, как сочетать загруженные skills
- **harness остаётся простым** — возможности добавляются новыми skills, а не правками ядра

## Частые ошибки

- **Загрузка всех skills при старте** — убивает смысл skill-системы. Используйте паттерн меню и грузите по требованию.
- **Монолитные skills** — skill «всё-в-одном» на 30 tools — это та же проблема «все tools upfront», только в маскировке. Держите skills сфокусированными: по 3–8 tools.
- **Отсутствие SKILL.md** — tools без документации заставляют модель гадать о конвенциях. SKILL.md не опционален; это мозг skill.
- **Нет механизма выгрузки** — если модель загрузит пять skills и не сможет их выгрузить, context быстро заполнится. Всегда давайте `unload_skill` рядом с `load_skill`.
- **Путаница имён skill и tool** — если skill назван `git` и содержит tool `git`, модель может попытаться вызвать имя skill как tool. Используйте разное именование: skill `git`, tools `git_status`, `git_diff` и т.д.

## Что почитать

- [OpenClaw Skills Architecture](https://docs.openclaw.ai) — production skill-система с меню skills и загрузкой по требованию
- [Anthropic: Tool Use Guide](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) — лучшие практики дизайна tools, применимые к skills
- [Model Context Protocol: Tools](https://modelcontextprotocol.io/) — открытый стандарт интеропа tools/skills между harness
