---
author: Harness Engineering Guide (RU)
title: "Cyrillic Tokenization: токен-экономика русского текста"
section: practice
description: "Почему русский текст стоит 1.2–1.8× токенов относительно английского на зарубежных моделях и как это проектировать: оценка budget, выбор токенизатора, сжатие context, ценовая оптимизация под русскоязычный harness."
category: Practice
date: "2026-07-19"
---

# Cyrillic Tokenization: токен-экономика русского текста

> **Главный инсайт:** «128K контекста» — это не про русский текст. На зарубежных frontier-моделях кириллица кодируется 1.5–3 байт-парами на символ против 1 для английского. Реальная ёмкость контекстного окна падает до 60–80%, а koszt удваивается. Х harness, не учитывающий Cyrillic penalty, переплачивает за токены и теряет instructions в compaction’е.

## Цена кириллицы

Большинство frontier-моделей (GPT, Claude, Gemini) используют **BPE-токенизаторы**, обученные преимущественно на английском. Для русского каждый символ часто превращается в отдельный токен — особенно редкие буквы (ъ, э, ф в окончания) и сочетания.

Эмпирические ориентиры (для `cl100k_base` и похожих):

| Текст | Знаков | Слов | Токенов | Знаков/токен |
|-------|--------|------|---------|--------------|
| English prose | 1000 | ~180 | ~210 | 4.8 |
| Русский prose | 1000 | ~150 | ~430 | 2.3 |
| Технический RU (с латинизмами) | 1000 | ~140 | ~360 | 2.8 |
| JSON с русскими значениями | 1000 | — | ~520 | 1.9 |

То есть **русская инструкция стоит в 1.8–2.3× дороже**, чем её английский эквивалент. Это критично для:

- **System prompt’ов** — стабильно в context, платите каждый ход
- **Tool descriptions** — каждый ход загружается заново
- **Few-shot examples** — раздутый budget съедает окно для реального диалога

## Слой 1. Измерение penalty под ваш tokenizер

Не доверяйте чужим таблицам — измеряйте свой случай.

```python
# Утилита для замера cyrillic penalty
import tiktoken

def measure_tokenization(text: str, encoding_name: str = "cl100k_base") -> dict:
    enc = tiktoken.get_encoding(encoding_name)
    tokens = enc.encode(text)
    return {
        "chars": len(text),
        "tokens": len(tokens),
        "chars_per_token": len(text) / max(1, len(tokens)),
        "tokens_per_word": len(tokens) / max(1, len(text.split())),
    }

# Сравните эквивалентные тексты
ru_sample = "Harness — это runtime-оболочка, превращающая модель в агента."
en_sample = "Harness is a runtime shell that turns a model into an agent."
print("RU:", measure_tokenization(ru_sample))
print("EN:", measure_tokenization(en_sample))
```

Запустите на **своём** корпусе (реальные промпты, documentation, error-логи) — penalty может оказаться от 1.2 до 2.5 в зависимости от латинизмов.

## Слой 2. Projecting token budget

Пересчитайте бюджет для русскоязычного harness с учётом penalty:

```python
def adjusted_budget(nominal_context: int, cyrillic_penalty: float = 1.8) -> dict:
    effective = int(nominal_context / cyrillic_penalty)
    return {
        "nominal": nominal_context,
        "effective_chars": effective * 4,  # ~4 знака на effective-токен
        "system_prompt_budget": int(effective * 0.15),
        "tools_budget": int(effective * 0.20),
        "memory_budget": int(effective * 0.25),
        "dialogue_budget": int(effective * 0.40),
    }

# Claude Sonnet 4 (200K nominal) под русский:
print(adjusted_budget(200_000, cyrillic_penalty=1.8))
# {'nominal': 200000, 'effective_chars': 444444, 'system_prompt_budget': 16666,
#  'tools_budget': 22222, 'memory_budget': 27777, 'dialogue_budget': 44444}
```

Если ваш system prompt + tools уже занимают 60K nominal на английском — на русском это **108K** effective, и от 200K-окна остаётся только ~92K под диалог и memory.

## Слой 3. Сжатие и bilingual strategy

### Перевод system-промптов на английский

Если система работает в русскоязычном UI, но system-промпт можно держать на английском — **переведите**. Claude/GPT отлично понимают английский system + русский user. Это экономит 30–50% токенов на самой стабильной части context’а.

```
System (English): You are an assistant for a Russian SaaS support team.
  Always reply in Russian. Use the tools to look up account state...

User (Russian): Привет, у меня не списалась подписка за июль.
```

### Tool descriptions — гибридный режим

Tool-имена и JSON-schema оставляйте на английском (они stable и парсятся моделью как код). Описания — двуязычно:

```json
{
  "name": "lookup_subscription",
  "description": "Find a user's subscription status by email or account_id. Найти статус подписки пользователя по email или account_id.",
  "parameters": {
    "type": "object",
    "properties": {
      "email": {"type": "string", "description": "User email / email пользователя"},
      "account_id": {"type": "string", "description": "Internal account ID / внутренний ID"}
    }
  }
}
```

Билингвость стоит +30% токенов на описание, но поднимает recall tool-calling у младших моделей на 15–25%.

### Few-shot examples — отбирать жёстче

На русском 3 few-shot’а съедают бюджет 5 английских. Сократите до 1–2 самых показательных, проверяя через eval, что recall не падает.

## Слой 4. Memory summarization под Cyrillic

[Memory & Context](/guide/memory-and-context) описывает двухуровневую memory. Под русский:

- **Chunk'и делайте короче** — 800–1500 токенов вместо 1500–2500 на английском
- **Саммари храните двуязычно** — decisions на английском (короткие термины), prose на русском
- **Compaction threshold ниже на 30%** — иначе русское наполнение переполнит окно быстрее, чем вы ожидаете

```python
def cyrillic_aware_compaction_threshold(nominal_threshold: int, penalty: float = 1.8) -> int:
    return int(nominal_threshold / penalty)

# Default 80K → под русский 44K
```

## Слой 5. Выбор модели под token-efficiency

Не все frontier-модели одинаково плохо кодируют кириллицу. Ориентиры (меняется с версией tokenizер’а):

| Семейство | Знаков/токен (RU) | Penalty vs EN |
|-----------|-------------------|---------------|
| GPT-4-class (tiktoken `o200k_base`) | 2.5–3.0 | 1.6–1.9 |
| Claude (Sonnet/Opus) | 2.3–2.8 | 1.7–2.1 |
| Gemini | 2.8–3.3 | 1.5–1.7 |
| YandexGPT | 3.8–4.5 | ~1.0 (нативный) |
| GigaChat | 3.5–4.2 | ~1.0 (нативный) |
| Qwen (multilingual) | 3.2–3.8 | 1.3–1.5 |

Для русскоязычных задач с большим context’ом — Qwen, YandexGPT или GigaChat экономически эффективнее зарубежных frontier. См. [Russian LLM в Harness](/guide/russian-llm-harness) и [YandexGPT и GigaChat](/guide/yandexgpt-and-gigachat).

## Слой 6. Cost monitoring

Включите в harness счётчик, который логирует **effective** токены, а не только nominal:

```python
def log_usage(provider: str, model: str, usage: dict, lang: str = "ru"):
    nominal = usage.get("total_tokens", 0)
    # Помечаем кириллический трафик для cost-анализа
    audit_logger.write({
        "ts": datetime.utcnow().isoformat(),
        "provider": provider,
        "model": model,
        "lang": lang,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total": nominal,
        # Приведённая cost-метрика для сравнения с EN-baseline
        "effective_en_equiv": int(nominal / 1.8) if lang == "ru" else nominal,
    })
```

Это позволит ответить на вопрос «сколько мы переплачиваем за русский» и принять решение о переключении части трафика на YandexGPT/GigaChat.

## Антипаттерны

- **Не измерять свой penalty** — чужие таблицы устаревают после каждого обновления tokenizер’а
- **Английский system prompt + английский user prompt для русскоязычной системы** — модель хуже работает с переводом туда-обратно
- **Полагать, что «контекст 200K» = 200K русского текста** — это 100–120K effective
- **Гнать всё через Claude/GPT «потому что качественнее»** — на рутинных русскоязычных задачах国产-модели могут быть в 3–5× дешевле при сопоставимом качестве

## Что почитать

- [Context Engineering](/guide/context-engineering) — управление токен-бюджетом
- [Memory & Context](/guide/memory-and-context) — компоновка context для длинных сессий
- [Russian LLM в Harness](/guide/russian-llm-harness) — специфика моделей
- [YandexGPT и GigaChat](/guide/yandexgpt-and-gigachat) — нативные русские tokenizер’ы
- [Eval Infrastructure Noise](/guide/eval-infrastructure) — почему настройки контекста меняют метрики
