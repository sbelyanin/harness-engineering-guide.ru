---
author: Nexu
---

# Context Engineering

> **Главный инсайт:** Модель не знает того, чего вы ей не сказали. Context engineering — дисциплина о том, что попадает в context window, в каком порядке и что отрезается, когда место заканчивается. Это самая высоколевериджная работа в harness engineering — важнее выбора модели, тюнинга промптов и дизайна tools.

## Проблема

Context window на 128K токенов кажется огромной, пока не начнёте её заполнять. Один крупный файл съедает 10K токенов. Двадцать схем tools — 3K. История диалога растёт линейно с каждым ходом. Через десяток ходов сложной coding-задачи вы уже принимаете жёсткие решения, что оставить, а что выбросить.

Context engineering — искусство этих решений. У него три столпа: **assembly** (что попадает внутрь), **compression** (что сжимается) и **budgeting** (как распределяется ёмкость).

## Система приоритетов сборки Context

Не весь context одинаково важен. Система приоритетов гарантирует, что при нехватке места выживают самые критичные данные:

| Приоритет | Категория | Типичные токены | Примечания |
|----------|----------|---------------|-------|
| 0 (высший) | System prompt | 300–800 | Идентичность, правила поведения, safety-ограничения |
| 1 | Схемы активных tools | 1 000–3 000 | Только загруженные skills, не все tools |
| 2 | Инструкция задачи | 200–1 000 | Текущий запрос пользователя + закреплённые цели |
| 3 | Саммари memory | 500–2 000 | Сжатая MEMORY.md + сегодняшний дневной лог |
| 4 | Инъецированные файлы | 2 000–20 000 | AGENTS.md, SKILL.md, релевантные исходники |
| 5 | Недавний диалог | 5 000–50 000 | Последние N ходов сообщений + результаты tools |
| 6 (низший) | Старый диалог | остаток | Более ранние ходы — первыми на сжатие или удаление |

Ассемблер идёт по списку сверху вниз, упаковывая контент, пока бюджет не иссякнет. Контент с более низким приоритетом усекается или исключается целиком.

```python
import tiktoken

encoder = tiktoken.encoding_for_model("gpt-4o")

def estimate_tokens(text: str) -> int:
    """Fast token estimation using tiktoken."""
    return len(encoder.encode(text))

class ContextAssembler:
    """Assemble context with priority-based token budgeting."""

    def __init__(self, max_tokens: int = 128_000, reserve: int = 4_096):
        self.max_tokens = max_tokens
        self.reserve = reserve  # Leave room for the model's response
        self.budget = max_tokens - reserve
        self.sections: list[tuple[int, str, str]] = []

    def add(self, priority: int, name: str, content: str):
        """Add a section. Lower priority number = higher importance."""
        self.sections.append((priority, name, content))

    def build(self) -> list[dict]:
        """Pack sections into messages within the token budget."""
        self.sections.sort(key=lambda s: s[0])
        messages = []
        used = 0

        for priority, name, content in self.sections:
            tokens = estimate_tokens(content)
            if used + tokens <= self.budget:
                messages.append({
                    "role": "system",
                    "content": f"[{name}]\n{content}",
                })
                used += tokens
            elif priority <= 2:
                # Critical sections get truncated rather than dropped
                remaining = self.budget - used
                truncated = self._truncate_to_tokens(content, remaining)
                if truncated:
                    messages.append({
                        "role": "system",
                        "content": f"[{name} (truncated)]\n{truncated}",
                    })
                    used += estimate_tokens(truncated)
            # Priority > 2: silently dropped when over budget

        return messages

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to fit within a token limit."""
        tokens = encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return encoder.decode(tokens[:max_tokens]) + "\n[...truncated]"
```

Параметр `reserve` легко упустить, но он критичен — нужно оставить пространство для ответа модели. Если упаковать context на 100%, модели некуда будет отвечать.

## Сжатие Context: три линии защиты

По мере развития session сырая история диалога растёт без ограничений. Три приёма не дают ей сожрать весь context window:

### Линия 1: Авто-decay

Старые сообщения естественно теряют актуальность. Простая стратегия decay выбрасывает сообщения за пределами фиксированного окна, оставляя только последние N ходов:

```python
def apply_decay(messages: list[dict], max_turns: int = 20) -> list[dict]:
    """Keep the system prompt and the last max_turns exchanges."""
    system = [m for m in messages if m["role"] == "system"]
    conversation = [m for m in messages if m["role"] != "system"]
    # Each "turn" is roughly a user + assistant + tool cycle
    if len(conversation) > max_turns * 3:
        conversation = conversation[-(max_turns * 3):]
    return system + conversation
```

### Линия 2: Пороговое сжатие

Когда суммарные токены переходят порог (например, 70% бюджета), сожмите старые ходы диалога в саммари, сохранив недавние дословно:

```python
def threshold_compress(
    messages: list[dict],
    budget: int,
    threshold: float = 0.7,
    keep_recent: int = 10,
) -> list[dict]:
    """Compress older messages when token usage exceeds threshold."""
    total = sum(estimate_tokens(m["content"]) for m in messages)
    if total < budget * threshold:
        return messages  # Under threshold, no compression needed

    system = [m for m in messages if m["role"] == "system"]
    conversation = [m for m in messages if m["role"] != "system"]

    old = conversation[:-keep_recent]
    recent = conversation[-keep_recent:]

    summary = summarize_with_llm(old)  # Use a fast, cheap model
    compressed = system + [{
        "role": "system",
        "content": f"[Conversation summary]\n{summary}",
    }] + recent

    return compressed
```

### Линия 3: Активная саммаризация

Для очень долгоиграющих задач периодически извлекайте ключевые факты и решения в накапливающийся документ-саммари. Это не автоматика — harness явно просит модель сделать checkpoint:

```python
SUMMARIZE_PROMPT = """Summarize the key decisions, findings, and current state 
from this conversation. Include: files modified, tests run, errors encountered, 
and the current plan. Be concise — under 500 words."""

def active_summarize(messages: list[dict]) -> str:
    """Ask the model to produce a checkpoint summary."""
    response = llm.chat(
        messages=messages + [{"role": "user", "content": SUMMARIZE_PROMPT}],
        max_tokens=1024,
    )
    return response.choices[0].message.content
```

## Токен-бюджет на практике

Реальная арифметика токенов для context window на 128K:

```
Общая ёмкость:                 128 000 токенов
Резерв под ответ:                -4 096
System prompt:                     -500
Схемы tools (12 tools):          -2 400
MEMORY.md:                       -1 200
AGENTS.md:                         -800
─────────────────────────────────────
Доступно под диалог:            119 004 токена

При ~3 токенах/слово это ~39 600 слов диалога.
Сессия программирования на 50 ходов с результатами tools: ~60 000 токенов.
→ Без сжатия вы упрётесь в бюджет около 35-го хода.
```

Вывод: сжатие обязательно для любой нетривиальной сессии.

## Паттерны инъекции Context

Context приходит не только из истории диалога. Пять распространённых паттернов инъекции:

| Паттерн | Когда | Пример |
|---------|------|---------|
| **Инъекция файлов** | Старт session | Загрузить AGENTS.md, MEMORY.md, релевантные исходники |
| **Инъекция memory** | Старт session | Сжатая долгосрочная memory + недавние дневные логи |
| **Инъекция результатов tool** | Внутри цикла | Добавить выводы tools как tool-role-сообщения |
| **Инъекция skill** | По требованию | Загрузить SKILL.md при активации skill |
| **Retrieval-инъекция** | На каждый запрос | RAG-результаты из vector-хранилища |

У каждой точки инъекции есть цена. Исходник на 200 строк — это ~800 токенов. Спекулятивная инъекция десяти файлов стоит 8K токенов ещё до начала диалога. Будьте осознанны: инъецируйте то, что нужно, а не то, что *может* понадобиться.

## Реализация скользящего окна

Скользящее окно (sliding window) хранит последние ходы нетронутыми и сжимает всё, что до границы окна. Это самая практичная стратегия для production-harness:

```python
class SlidingWindowContext:
    """Maintain a sliding window over conversation history."""

    def __init__(self, window_size: int = 15, max_tokens: int = 128_000):
        self.window_size = window_size
        self.max_tokens = max_tokens
        self.summary = ""
        self.messages: list[dict] = []

    def add(self, message: dict):
        self.messages.append(message)
        conversation = [m for m in self.messages if m["role"] != "system"]
        if len(conversation) > self.window_size * 3:
            self._compress()

    def _compress(self):
        """Move older messages into a rolling summary."""
        conversation = [m for m in self.messages if m["role"] != "system"]
        system = [m for m in self.messages if m["role"] == "system"]

        old = conversation[:-(self.window_size * 3)]
        recent = conversation[-(self.window_size * 3):]

        new_summary = summarize_with_llm(
            [{"role": "system", "content": self.summary}] + old
        )
        self.summary = new_summary
        self.messages = system + recent

    def get_messages(self) -> list[dict]:
        """Return context-ready message list."""
        result = [m for m in self.messages if m["role"] == "system"]
        if self.summary:
            result.append({
                "role": "system",
                "content": f"[Conversation history summary]\n{self.summary}",
            })
        result.extend(m for m in self.messages if m["role"] != "system")
        return result
```

## Частые ошибки

- **Считать весь context одинаково приоритетным** — system prompt и инструкции задачи должны выживать; старый диалог можно сжать. Без приоритетов вы либо тратите место на устаревшие сообщения, либо теряете критичные инструкции.
- **Слишком агрессивное сжатие** — саммаризация теряет данные. Если сжать результат tool, где был путь к файлу, модель позже его галлюцинирует. Держите недавние ходы дословно.
- **Игнорирование подсчёта токенов** — оценка на глаз «вроде коротко» быстро ломается. Используйте реальный подсчёт (tiktoken, модельные токенизаторы) для бюджетирования.
- **Одноразовая сборка context** — собрать context один раз на старте и не обновлять значит, что после первого tool-вызова модель работает с устаревшими данными. Пересобирайте context каждый ход.

## Что почитать

- [Karpathy: «Context Engineering is the New Prompt Engineering»](https://x.com/karpathy/status/1937902263428948034) — почему сборка context важнее трюков с промптами
- [Letta: MemGPT and the Future of Agent Memory](https://www.letta.com/blog/memgpt) — управление memory по мотивам ОС с виртуальным context
- [OpenAI: Managing Tokens](https://platform.openai.com/docs/guides/text-generation#managing-tokens) — основы подсчёта токенов
