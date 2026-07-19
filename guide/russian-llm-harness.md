---
author: Harness Engineering Guide (RU)
title: "Russian LLM в Harness"
section: practice
description: "Особенности построения harness под русскоязычные модели: отличия в токенизации, tool-calling, культурном контексте и требованиях к безопасности."
category: Practice
date: "2026-07-18"
---

# Russian LLM в Harness

> **Главный инсайт:** Перенос harness с западных frontier-моделей на русскоязычные LLM требует не просто замены API-ключа. Русский язык меняет токен-бюджет, качество tool-calling, чувствительность к system-промптам и ожидания пользователя. Harness, который работал на Claude, может деградировать на GigaChat/YandexGPT до уровня чат-бота, если не адаптировать context и guardrails.

## Что отличает русскоязычные LLM

### Токенизация и длина контекста

Русский текст обычно требует больше токенов на ту же семантическую нагрузку, чем английский. Это влияет на:

- **Context window** — один и тот же объём инструкций занимает 1.2–1.5× токенов
- **Tool descriptions** — схемы tools с русскими описаниями растут в размере
- **Memory summarization** — саммари на русском может терять детали при агрессивном сжатии

### Tool-calling и форматы ответа

Не все русскоязычные модели поддерживают native function calling. Возможны варианты:

- **Native tool-calling** — модель возвращает структурированный вызов (лучший случай)
- **JSON-mode** — модель выдаёт JSON, который harness парсит в tool-call
- **Text-mode** — требуется parsing layer: извлечь намерение из текста и смаппить на tool

Harness должен быть готов ко всем трём режимам и уметь failover между ними.

### Культурный и юридический контекст

- **Регуляторика** — обработка персональных данных, требования к хранению логов
- **Локальные сервисы** — интеграция с Яндекс.Календарём, Telegram, VK, email на Mail.ru
- **Языковые нормы** — формальность/неформальность, обращение на «вы», местные идиомы

## Адаптация harness

### 1. System prompt на русском

System prompt должен быть написан на русском, даже если часть примеров кода или инструкций взяты из англоязычных источников. Перевод «в лоб» часто ломает тон и инструкции.

### 2. Примеры вызовов tools

Few-shot примеры tool-calling должны содержать русскоязычные запросы и ожидаемые ответы. Это особенно важно для моделей, дообученных преимущественно на англоязычных данных.

### 3. Token budget под русский

Рекомендуется увеличить резерв под system prompt и memory на 20–30% относительно англоязычной версии harness. Иначе критичные инструкции могут вытесняться раньше.

### 4. Guardrails локального контекста

- Фильтрация запрещённого контента по российским нормам
- Защита от prompt injection с учётом русскоязычных паттернов
- Локальная анонимизация персональных данных

## Эталонная конфигурация `harness.toml`

Минимальный runnable-конфиг под RU-модели. Покрывает: multi-provider failover, токен-бюджет под кириллицу, text-mode fallback для tool-calling, pseudonymization перед внешними вызовами.

```toml
# harness.toml — эталонная конфигурация для русскоязычного harness
# См. https://harness-guide.com/guide/russian-llm-harness

[meta]
lang = "ru"
timezone = "Europe/Moscow"
# 152-ФЗ: какие категории ПДн обрабатывает harness (для аудита)
pdn_categories = ["contact", "payment_metadata"]

# Провайдеры в порядке failover. Первый рабочий побеждает.
[[providers]]
name = "yandexgpt"
model = "yandexgpt-lite"
endpoint = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
# IAM-токен протухает за 12 часов — renewer крутится отдельным процессом
iam_token_env = "YANDEX_IAM_TOKEN"
folder_id_env = "YANDEX_FOLDER_ID"
timeout_ms = 15000
retry = { max_attempts = 2, backoff_ms = 500 }

[[providers]]
name = "gigachat"
model = "GigaChat-Pro"
endpoint = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
auth_env = "GIGACHAT_AUTH"
scope = "BUSINESS"  # НЕ _PERS — иначе violation compliance
timeout_ms = 15000

[[providers]]
name = "local-vllm"
model = "Qwen/Qwen2.5-32B-Instruct"
endpoint = "http://localhost:8000/v1/chat/completions"
# OpenAI-compatible API; для air-gap см. guide/open-source-llm-stack
timeout_ms = 30000

[context]
# Кириллица занимает 1.2–1.5× больше токенов — резерв увеличен
max_total_tokens = 32000
reserve_system_prompt = 4000   # +30% относительно EN-базовой конфигурации
reserve_memory = 6000
reserve_tools_output = 8000

[system_prompt]
# System prompt пишется на русском. Перевод «в лоб» с EN часто ломает тон.
text = """
Ты — Russian-speaking AI-агент в harness.
Отвечай на русском. Обращайся к пользователю на «вы».
При вызове tools возвращай структурированный JSON согласно схеме.
Не передавай персональные данные в fields, не помеченные как safe_for_external.
"""

[tools]
# Младшие RU-модели плохо переваривают $ref и oneOf — упрощаем схему.
schema_simplification = true
# text-mode fallback: если native tool-call не вернулся, парсим JSON из ответа
text_mode_fallback = true
text_mode_format = "```json\\n{...}\\n```"

[guardrails]
# RU-специфичные паттерны prompt injection
prompt_injection_patterns = [
  "игнорируй.*инструкции",
  "забудь.*предыдущие.*правила",
  "ты.*на.*самом.*деле",
]
# ПДн-сканер перед записью в memory и перед внешними LLM-вызовами
pdn_filter = { enabled = true, mask_strategy = "pseudonymize" }

[memory]
# TTL под право на удаление (152-ФЗ ст. 17)
short_term_ttl_hours = 24
long_term_ttl_days = 90
# Cleanup-процесс отдельной cron'ом — иначе agent-loop тормозит
cleanup_cron = "0 3 * * *"
```

### Что здесь важного

- **`scope = "BUSINESS"` для GigaChat** — `_PERS` привязан к физлицу и violates compliance (см. [152-ФЗ](/guide/compliance-152fz))
- **`schema_simplification`** — младшие модели плохо переваривают JSON Schema с `$ref`/`oneOf`; упрощаем до `enum` + явных полей
- **`text_mode_fallback`** — если native tool-call не вернулся, harness парсит fenced JSON из текстового ответа
- **`pdn_filter`** — pseudonymization перед любым вызовом, покидающим perimeter (см. [Guardrails](/guide/guardrails))

## Что почитать

- [Что такое Harness?](/guide/what-is-harness) — базовая архитектура
- [Tool System](/guide/tool-system) — как описывать tools
- [Context Engineering](/guide/context-engineering) — управление токен-бюджетом
