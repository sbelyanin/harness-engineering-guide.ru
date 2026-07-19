---
title: "Что такое Harness?"
section: getting-started
author: Nexu
---

# Что такое Harness?

> **Главный инсайт:** Модели commoditizing — GPT, Claude и Gemini сходятся по возможностям. Настоящий moat — это Harness: то, как вы оркестриуете Context, Memory, Tool и lifecycle агента, определяет, получите ли вы чат-бота или production-агента.

## Определение

**Harness** — это runtime-оболочка, превращающая голую языковую модель в **Agent**: автономную систему, способную воспринимать окружение, принимать решения и выполнять действия за несколько шагов для достижения цели.

Важно отличать здесь смысл слова «агент» от более раннего употребления. В 2023–2024 годах «агент» обычно означал *модель плюс tools* — вы давали GPT tool для веб-поиска и называли это агентом. Агенты, на которые рассчитано harness engineering, принципиально сложнее:

| Компонент | «Агент» 2023 | Агент эпохи Harness |
|-----------|-------------|-------------------|
| Модель | ✅ LLM | ✅ LLM |
| Tools | ✅ Function calling | ✅ Динамическая Tool-система |
| Memory | ❌ Stateless | ✅ Persistent-память между сессиями |
| Управление Context | ❌ Наивное | ✅ Сборка Context по приоритетам |
| Оркестрация | ❌ Один шаг | ✅ Agentic Loop с восстановлением после ошибок |
| Среда выполнения | ❌ Host-процесс | ✅ Sandboxed-runtime |
| Guardrails | ❌ Минимальные | ✅ Модель разрешений + trust-границы |

Harness — это инженерный слой, который обеспечивает всё это. Без него у вас чат-бот, умеющий вызывать функции. С ним — агент, способный самостоятельно разобраться в кодовой базе, поправить баги в нескольких файлах и закоммитить результат.

## Анатомия Harness

Любой harness, независимо от реализации, содержит четыре подсистемы:

```
┌──────────────────────────────────────────────┐
│                   HARNESS                     │
│                                               │
│  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Agentic  │  │   Tool   │  │  Memory &  │  │
│  │   Loop   │  │  System  │  │  Context   │  │
│  └──────────┘  └──────────┘  └────────────┘  │
│                                               │
│  ┌────────────────────────────────────────┐   │
│  │            Guardrails                  │   │
│  └────────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
```

1. **Agentic Loop** — цикл think → act → observe, который управляет всем поведением агента. Модель рассуждает, вызывает tool, наблюдает результат и повторяет цикл, пока задача не будет выполнена.

2. **Tool System** — реестр возможностей, доступных агенту: файловый I/O, выполнение команд в shell, веб-поиск, API-вызовы. Tools могут быть статическими (загружаются при старте) или динамическими (подгружаются по требованию через skill-меню).

3. **Memory & Context** — система, которая решает, что модель может *видеть*. Сюда входят три отдельных вопроса:
   - **Context** — что попадает в текущий API-вызов (system prompt, tools, файлы, история диалога)
   - **Memory** — что сохраняется между сессиями (MEMORY.md, дневные логи, выученные предпочтения)
   - **Session** — граница одного запуска агента (история сообщений, результаты tools, scratch-состояние)

4. **Guardrails** — границы разрешений, enforcement sandbox и safety-ограничения. Что агент может и чего не может делать, и как предотвратить обход этих границ через prompt injection.

Эти четыре подсистемы подробно разбираются в разделе [Базовые концепции](/guide/agentic-loop).

## Минимальный пример

Простейший harness — это цикл. Он production-неполноценен, но структурно корректен:

```python
import openai

client = openai.OpenAI()
tools = [{"type": "function", "function": {"name": "read_file", ...}}]

messages = [{"role": "system", "content": "You are a coding agent."}]
messages.append({"role": "user", "content": user_input})

# The agentic loop
while True:
    response = client.chat.completions.create(
        model="gpt-4o", messages=messages, tools=tools
    )
    msg = response.choices[0].message
    messages.append(msg)

    if not msg.tool_calls:
        print(msg.content)  # Done — model has no more actions
        break

    for call in msg.tool_calls:
        result = execute_tool(call.function.name, call.function.arguments)
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": result
        })
    # Loop back — model sees the tool results and decides next action
```

Любой harness — от скрипта на 50 строк до Claude Code — это вариация этого цикла. Сложность возникает в том, что вы строите *вокруг* него: сборка context, персистентность memory, оркестрация skill, восстановление после ошибок и sandboxing.

## Harness vs. Framework vs. Runtime

Эти три термина часто путают. Это разные слои:

| Термин | Роль | Примеры |
|------|------|----------|
| **Harness** | Код оркестрации, оборачивающий модель в агента | Claude Code, Codex CLI, OpenClaw |
| **Framework** | Библиотека со строительными блоками для создания harness | LangChain, CrewAI, AutoGen |
| **Runtime** | Постоянный процесс, который держит harness запущенным, управляет его lifecycle и связывает с внешним миром | OpenClaw runtime, Docker-контейнер, systemd-сервис |

Framework помогает *построить* harness. Runtime *хостит* harness — поддерживает его жизнь, обрабатывает переподключение, планирует heartbeats и маршрутизирует сообщения. Сам harness — это логика оркестрации: как собирается context, какие tools загружаются и как ведёт себя agentic loop.

## Частые ошибки

- **Валить всё на модель, когда проблема в harness** — когда агент ошибается, обычно дело в context (загружены не те файлы, не хватает инструкций) или в tool (неверная схема, тихие ошибки), а не в способностях модели.
- **Over-engineering с первого дня** — начните с минимального цикла выше. Добавляйте memory, когда нужна кросс-сессионная память. Добавляйте skills, когда tools стало слишком много. Добавляйте guardrails при выходе в production.
- **Считать context window безграничным** — модель может рассуждать только о том, что попало в её context. Если критичная информация не собрана в промпт, её для модели фактически не существует.

## Что почитать

- [OpenAI: Harness Engineering](https://openai.com/index/harness-engineering/) — пост, который назвал новую дисциплину
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — паттерны Anthropic для production-агентов
