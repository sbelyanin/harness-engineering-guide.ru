---
title: "Ваш первый Harness"
section: getting-started
author: Nexu
---

# Ваш первый Harness

> **Главный инсайт:** Harness — это просто цикл: вызвать модель, выполнить tool-вызовы, вернуть результаты обратно, повторить. Рабочий вариант укладывается в 50 строк Python. Понимание этого цикла снимает налёт мистики со всех agent-фреймворков.

Большинство туториалов по агентам начинаются с фреймворка — LangChain, CrewAI, AutoGen. Но фреймворки скрывают механизм. Сборка harness с нуля показывает, что именно происходит: agentic loop, сборка context и процесс принятия решений моделью. Разобравшись с этим, любой фреймворк становится прозрачным.

## Полный Harness

Перед вами полностью рабочий harness с двумя tools (чтение и запись файла). Скопируйте и запустите.

### Требования

```bash
pip install openai
export OPENAI_API_KEY="sk-your-key-here"
```

### Код

```python
#!/usr/bin/env python3
"""A complete agent harness in ~50 lines. Run: python harness.py"""

import json
import os
from openai import OpenAI

client = OpenAI()
MODEL = "gpt-4o-mini"  # Cheap and fast for learning
MAX_TURNS = 15

# --- System prompt ---
SYSTEM = """You are a helpful file assistant. You can read and write files.
When asked to work with files, use the tools provided.
Always confirm what you did after completing a task."""

# --- Tool definitions ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file at the given path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file (creates or overwrites)",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"},
                    "content": {"type": "string", "description": "Content to write"}
                },
                "required": ["path", "content"]
            }
        }
    }
]

# --- Tool execution ---
def execute_tool(name: str, args: dict) -> str:
    try:
        if name == "read_file":
            with open(args["path"], "r") as f:
                return f.read()
        elif name == "write_file":
            os.makedirs(os.path.dirname(args["path"]) or ".", exist_ok=True)
            with open(args["path"], "w") as f:
                f.write(args["content"])
            return f"Wrote {len(args['content'])} chars to {args['path']}"
        else:
            return f"Error: Unknown tool '{name}'"
    except Exception as e:
        return f"Error: {e}"

# --- The tool loop ---
def run(user_message: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user_message}
    ]

    for turn in range(MAX_TURNS):
        response = client.chat.completions.create(
            model=MODEL, messages=messages, tools=TOOLS
        )
        msg = response.choices[0].message
        messages.append(msg)

        # No tool calls → model is done
        if not msg.tool_calls:
            return msg.content

        # Execute each tool call
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            print(f"  🔧 {tc.function.name}({args})")
            result = execute_tool(tc.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result
            })

    return "Max turns reached."

# --- Main ---
if __name__ == "__main__":
    print("🤖 File Agent (type 'quit' to exit)")
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        response = run(user_input)
        print(f"\nAgent: {response}")
```

### Запуск

```bash
python harness.py
```

```
🤖 File Agent (type 'quit' to exit)

You: Create a file called hello.txt with a haiku about programming

  🔧 write_file({'path': 'hello.txt', 'content': 'Semicolons fall\nLike rain upon the server\nCompile error: none'})

Agent: I've created hello.txt with a programming haiku!

You: Read it back to me

  🔧 read_file({'path': 'hello.txt'})

Agent: Here's the content of hello.txt:
"Semicolons fall / Like rain upon the server / Compile error: none"
```

## Анатомия Harness

Весь harness состоит из четырёх компонентов:

```
┌────────────────────────────────┐
│         System Prompt          │  ← Кто этот агент
├────────────────────────────────┤
│        Tool Definitions        │  ← Что он умеет (JSON-схема)
├────────────────────────────────┤
│        Tool Execution          │  ← Как tools реально выполняются
├────────────────────────────────┤
│          Tool Loop             │  ← Цикл: think → act → observe
└────────────────────────────────┘
```

**System prompt**: задаёт личность агента и ограничения. Это самый дешёвый и самый высоколевериджный элемент — одно изменённое предложение здесь может полностью поменять поведение.

**Tool definitions**: JSON-схемы, которые модель читает, чтобы понять, какие tools существуют. Модель никогда не видит ваш Python-код — только описания и схемы параметров.

**Tool execution**: ваш код, который реально выполняет действия. Модель выдаёт структурированный JSON; вы парсите его и делаете настоящую работу.

**Tool loop**: оркестратор. Вызвать модель, проверить наличие tool-вызовов, выполнить их, вернуть результаты обратно. Повторять, пока модель не ответит простым текстом.

## Добавляем третий Tool

Хотите добавить shell-команды? Просто добавьте определение tool и обработчик:

```python
# Add to TOOLS list:
{
    "type": "function",
    "function": {
        "name": "run_shell",
        "description": "Run a shell command and return stdout/stderr",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"}
            },
            "required": ["command"]
        }
    }
}

# Add to execute_tool():
elif name == "run_shell":
    import subprocess
    r = subprocess.run(args["command"], shell=True, capture_output=True, text=True, timeout=30)
    return r.stdout + r.stderr
```

Цикл не меняется. Модель сама находит и начинает использовать новый tool.

## Смена модели

Harness не привязан к конкретной модели. Переключитесь на Claude от Anthropic, сменив клиент:

```python
from anthropic import Anthropic

client = Anthropic()

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system=SYSTEM,
    messages=messages,
    tools=[{
        "name": t["function"]["name"],
        "description": t["function"]["description"],
        "input_schema": t["function"]["parameters"]
    } for t in TOOLS]
)

# Parse tool calls from response.content blocks
for block in response.content:
    if block.type == "tool_use":
        result = execute_tool(block.name, block.input)
```

Тот же цикл. Те же tools. Другая модель.

## Чего не хватает (и что дальше)

Этот harness работает, но production-агентам нужно больше:

| Возможность | Этот harness | Production-harness |
|---------|-------------|-------------------|
| Memory | Нет (stateless) | MEMORY.md + дневные логи |
| Управление Context | Вся история целиком | Windowing по приоритетам |
| Восстановление после ошибок | Базовый try/catch | Retry + эскалация |
| Security | Нет | Sandboxed-выполнение |
| Загрузка Tools | Все сразу | Skills по требованию |

Каждый из этих пунктов разобран в остальных статьях гайда.

## Частые ошибки

- **Забыли добавить assistant-сообщение** — если не положить `msg` в `messages` перед результатами tool, модель теряет контекст того, что она запрашивала. Всегда сначала добавляйте полный ответ модели.
- **Неправильно сериализуете результаты tool** — результаты tool должны быть строками. Если ваш tool возвращает dict, сделайте `json.dumps()`. Возврат сырого Python-объекта приведёт к крашу.
- **Нет лимита итераций** — без `MAX_TURNS` запутавшаяся модель может зациклиться навсегда, сжигая токены. Всегда ставьте ограничение.

## Что почитать

- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling) — официальная документация по определению tools
- [Anthropic Tool Use Guide](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) — аналог у Claude
- [ReAct Paper](https://arxiv.org/abs/2210.03629) — академический фундамент Tool Loop'ов
