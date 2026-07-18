---
author: Nexu
---

# Memory & Context

> **Главный инсайт:** Модель знает только то, что попадает в её context window. Memory — способ перекинуть мост между тем, что модели *нужно знать*, и тем, что она *может увидеть* за один API-вызов. Решить это правильно — самая высоколевериджная задача в harness engineering.

## Три разных понятия

Эти термины часто смешивают, но у них разные роли:

| Понятие | Область | Персистентность | Пример |
|---------|-------|-------------|---------|
| **Context** | Один API-вызов | Нет — пересобирается каждый ход | System prompt + tools + недавние сообщения + релевантные файлы |
| **Session** | Один диалог или задача | In-memory, теряется при рестарте | История сообщений, результаты tool-вызовов, рабочее состояние |
| **Memory** | Кросс-сессионная, бессрочная | Пишется на диск | MEMORY.md, дневные логи, выученные предпочтения |

**Context** — это «рабочая память» модели: всё, что собирается в один промпт. **Session** — состояние текущего взаимодействия. **Memory** — то, что переживает завершение сессии.

## Сборка Context

Каждый ход agentic loop начинается со сборки context. Это задача упаковки по приоритетам — у вас фиксированный токен-бюджет, и нужно решить, что попадёт внутрь:

```
Context Window (e.g., 128K tokens)
┌─────────────────────────────────┐
│  System Prompt        (~500)    │  ← Всегда включается, высший приоритет
│  Tool Schemas         (~2000)   │  ← Только активные tools
│  Memory Summary       (~1000)   │  ← Сжатая долгосрочная memory
│  Relevant Files       (~5000)   │  ← Контекст под задачу
│  Conversation History (~varies) │  ← Растёт со временем, нужна обрезка
│  [Remaining Budget]             │  ← Доступно под новый контент
└─────────────────────────────────┘
```

Система приоритетов определяет, что попадает внутрь, когда места мало:

```python
class ContextAssembler:
    def __init__(self, max_tokens: int = 128_000):
        self.max_tokens = max_tokens
        self.sections = []  # (priority, name, content)

    def add(self, priority: int, name: str, content: str):
        self.sections.append((priority, name, content))

    def build(self) -> list[dict]:
        # Sort by priority (lower = higher priority)
        self.sections.sort(key=lambda x: x[0])
        messages = []
        used_tokens = 0
        for priority, name, content in self.sections:
            token_count = estimate_tokens(content)
            if used_tokens + token_count > self.max_tokens:
                break  # Budget exceeded — skip lower-priority content
            messages.append({"role": "system", "content": f"[{name}]\n{content}"})
            used_tokens += token_count
        return messages
```

## Управление Session

Session — граница одного запуска агента. Она хранит:

- **Историю сообщений** — весь диалог, включая tool-вызовы и результаты
- **Рабочее состояние** — какие файлы открыты, какие skills загружены, текущий прогресс задачи
- **Scratch-пространство** — временные данные, которые агент сгенерировал, но не закоммитил

Ключевое решение в дизайне session — **когда её чистить**. Несколько вариантов:

| Стратегия | Поведение | Сценарий |
|----------|----------|----------|
| **Per-task** | Новая session на каждый запрос пользователя | Stateless-ассистент |
| **Per-conversation** | Session живёт между ходами в одном чате | Интерактивное программирование |
| **Persistent** | Session переживает рестарт процесса | Долгоиграющий фоновый агент |

Persistent-сессии требуют сериализации — записи состояния session на диск для восстановления. Здесь session и memory пересекаются: всё, что стоит сохранить между рестартами, лучше писать в memory-файл, а не держать в состоянии session.

## Архитектура Memory

Проверенная архитектура memory использует два уровня:

### Уровень 1: Дневные логи

Сырые хронологические записи того, что произошло. Пишутся в течение сессии, не курируются:

```markdown
<!-- memory/2026-04-15.md -->
# 2026-04-15

## 14:30 — Refactored auth module
- Moved JWT validation from middleware to dedicated service
- Tests passing (23/23)
- User prefers explicit error messages over error codes

## 16:00 — Deploy to staging
- Used blue-green deployment
- Rollback plan: revert commit abc123
```

### Уровень 2: Долгосрочная Memory

Курируемые, дистиллированные знания. Обновляются периодически (не каждый ход):

```markdown
<!-- MEMORY.md -->
# Long-term Memory

## User Preferences
- Prefers explicit error messages over error codes
- Uses pytest, not unittest
- Deploy strategy: blue-green with rollback plan

## Project Knowledge
- Auth module: JWT validation in /src/services/auth.py
- Database: PostgreSQL 15, migrations in /db/migrations/
- CI: GitHub Actions, ~3min build time

## Lessons Learned
- Always run tests before committing (broke build on 4/10)
- User dislikes verbose output — keep summaries under 5 lines
```

Ключевой инсайт: дневные логи дёшево писать (просто дописать в конец). Долгосрочная memory требует суждения (что стоит сохранить?). Production-harness пишут дневные логи автоматически и курируют MEMORY.md периодически — по расписанию или когда агент фиксирует значимые выводы.

## Цикл чтения/записи Memory

```python
def session_startup(memory_dir: str) -> str:
    """Read memory at session start."""
    sections = []
    # Always read long-term memory
    memory_path = os.path.join(memory_dir, "MEMORY.md")
    if os.path.exists(memory_path):
        sections.append(open(memory_path).read())
    # Read recent daily logs (today + yesterday)
    for days_ago in [0, 1]:
        date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        daily_path = os.path.join(memory_dir, f"memory/{date}.md")
        if os.path.exists(daily_path):
            sections.append(open(daily_path).read())
    return "\n---\n".join(sections)
```

## Паттерн AGENTS.md

Родственный, но отдельный файл — AGENTS.md: plain-text-файл, который определяет, как агент должен *себя вести* (а не что он *помнит*). Положите его в любую директорию, и совместимый harness подхватит его автоматически:

```markdown
<!-- AGENTS.md -->
# Behavior

- You are a Python backend engineer
- Use pytest for all tests
- Follow Google style docstrings
- Never modify files in /config/ without asking

# Tools

- Prefer `ruff` over `pylint` for linting
- Use `uv` for package management
```

AGENTS.md **декларативен** (что делать), тогда как MEMORY.md **опытен** (что произошло). Оба инъектируются в context при старте session, но служат разным целям.

## Частые ошибки

- **Считать context безграничным** — даже 128K токенов быстро заполняются схемами tools, содержимым файлов и историей диалога. Планируйте токен-бюджет явно.
- **Никогда не обрезать историю session** — диалог на 50 ходов накапливает избыточный контент. Компактьте или саммаризуйте старые ходы, чтобы освободить место.
- **Писать memory слишком активно** — не каждый ход порождает знания, достойные сохранения. Избыточная запись создаёт шум, который размывает полезную информацию.
- **Забыть прочитать memory при старте** — агент без чтения memory фактически амнезиак. Это самый частый конфиг-баг.

## Что почитать

- [Letta: MemGPT and the Future of Agent Memory](https://www.letta.com/blog/memgpt) — управление memory для агентов по мотивам ОС
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — паттерны memory в production
