---
title: "Agentic Loop"
section: core-concepts
author: Nexu
---

# Agentic Loop

> **Главный инсайт:** Любой агент — это цикл: think, act, observe, repeat. Сам цикл тривиален. Production-уровнем его делает то, как вы обрабатываете крайние случаи: когда останавливаться, что делать при падении tools и как предотвратить бесконечные зацикливания.

## Паттерн

Agentic Loop (он же паттерн ReAct — Reason + Act) — это фундаментальный цикл выполнения любого AI-агента. Модель генерирует ответ, опционально вызывает один или несколько tools, наблюдает результаты и повторяет цикл, пока задача не будет выполнена.

```
┌─────────────┐
│   Reason    │◄──────────────────┐
│  (LLM call) │                   │
└──────┬──────┘                   │
       │                          │
       ▼                          │
  ┌─────────┐    Tools нет    ┌────┴─────┐
  │  Tools? ├───────────────►│  Output  │
  └────┬────┘                └──────────┘
       │ Есть
       ▼
  ┌─────────┐
  │ Execute │
  │  tools  │
  └────┬────┘
       │
       ▼
  ┌─────────┐
  │ Observe │
  │ results ├─────────────────────┘
  └─────────┘
```

Это отличается от простого API tool-calling. Один tool-вызов — это one-shot: модель говорит «вызови эту функцию», вы возвращаете результат. **Agentic loop** запускает этот процесс многократно — модель видит результат, понимает, что нужно больше информации, вызывает другой tool, видит *тот* результат и продолжает, пока не наберёт достаточно context, чтобы выдать финальный ответ.

## Реализация

Минимальный agentic loop на Python:

```python
def agentic_loop(messages: list, tools: list, max_turns: int = 25) -> str:
    """Run the agentic loop until the model produces a final text response."""
    for turn in range(max_turns):
        response = llm.chat(messages=messages, tools=tools)
        assistant_msg = response.choices[0].message
        messages.append(assistant_msg)

        # Exit condition: no tool calls means the model is done
        if not assistant_msg.tool_calls:
            return assistant_msg.content

        # Execute each tool call and append results
        for tool_call in assistant_msg.tool_calls:
            result = dispatch_tool(tool_call)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result)
            })

    raise AgentLoopError(f"Agent did not complete within {max_turns} turns")
```

Параметр `max_turns` критичен. Без него запутавшаяся модель будет циклиться бесконечно — вызывать один и тот же tool, получать ту же ошибку и жечь токены. Это простейший guardrail, и он должен быть всегда.

## Параллельные tool-вызовы

Современные API поддерживают **параллельные tool-вызовы** (parallel tool calls) — модель может запросить несколько tools в одном ответе. Это не просто оптимизация, это меняет поведение агента. Модели, которой нужно прочитать три файла, проще запросить все три сразу, а не по очереди:

```python
# A single assistant message might contain:
# tool_calls = [read_file("a.py"), read_file("b.py"), read_file("c.py")]

for tool_call in assistant_msg.tool_calls:
    result = dispatch_tool(tool_call)
    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": str(result)
    })
# All three results are appended, then the model sees them all at once
```

## Бюджет ходов и условия выхода

Циклу нужны чёткие условия выхода помимо `max_turns`:

| Условие | Действие |
|-----------|--------|
| В ответе нет tool-вызовов | Вернуть текст — агент закончил |
| Достигнут лимит ходов | Бросить ошибку или принудительно саммаризовать |
| Превышен токен-бюджет | Запустить сжатие context, затем продолжить |
| Подряд идущие одинаковые tool-вызовы | Вероятно, застрял — эскалировать или прервать |
| Сигнал прерывания от человека | Поставить цикл на паузу, показать текущее состояние |

```python
def detect_loop(messages: list, window: int = 3) -> bool:
    """Detect if the agent is stuck calling the same tool repeatedly."""
    recent_calls = []
    for msg in messages[-window * 2:]:
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            recent_calls.extend(
                (tc.function.name, tc.function.arguments) for tc in msg.tool_calls
            )
    if len(recent_calls) >= window:
        return len(set(recent_calls[-window:])) == 1
    return False
```

## Streaming в цикле

Production-harness стримят вывод модели токен за токеном, пока цикл крутится. Это важно для UX — человек видит, как агент «думает» в реальном времени, а не пялится в пустой экран:

```python
for turn in range(max_turns):
    stream = llm.chat(messages=messages, tools=tools, stream=True)

    tool_calls = []
    text_chunks = []

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            text_chunks.append(delta.content)
            emit_to_user(delta.content)  # Real-time streaming
        if delta.tool_calls:
            accumulate_tool_calls(tool_calls, delta.tool_calls)

    if not tool_calls:
        return "".join(text_chunks)

    # Execute tools and continue loop
    ...
```

## Частые ошибки

- **Нет лимита ходов** — самый частый баг в harness. Всегда ставьте максимум.
- **Глушение ошибок tool** — если tool падает тихо, модель будет ретраить или галлюцинировать успех. Всегда возвращайте сообщения об ошибках как результаты tool, чтобы модель могла адаптироваться.
- **Добавление сырых результатов** — большие выводы tools (целые файлы, API-ответы) раздувают context window. Усекайте или саммаризуйте перед добавлением.
- **Игнорирование параллельных вызовов** — если ваш цикл обрабатывает tool-вызовы последовательно, а модель выдала их параллельно, можно создать ложные зависимости порядка.

## Что почитать

- [Yao et al., «ReAct: Synergizing Reasoning and Acting»](https://arxiv.org/abs/2210.03629) — оригинальная статья, формализующая паттерн Reason + Act
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) — практические паттерны для production-циклов
