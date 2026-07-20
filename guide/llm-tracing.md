---
author: Harness Engineering Guide (RU)
title: "LLM Tracing: OpenTelemetry GenAI semantic conventions"
section: practice
description: "Distributed tracing для harness: OpenTelemetry GenAI semantic conventions, span attributes для model calls, context propagation через agent-loop, sampling стратегии, цена trace'ов и как её контролировать."
category: Practice
date: "2026-07-23"
---

# LLM Tracing: OpenTelemetry GenAI semantic conventions

> **Главный инсайт:** Trace в harness — это не «что вызвало что», как в обычных микросервисах, а **как модель пришла к ответу**: какие tool'ы вызывала, что они вернули, какой prompt был отправлен на какой iteration. Это единственный способ понять, почему session стоила $2 и заняла 40 секунд.

## Почему трейсинг особенно важен для harness

В классическом сервисе trace отвечает на вопрос «где время?». В harness — на гораздо более широкий набор:

- **Почему так долго?** Agent-loop сделал 7 итераций вместо ожидаемых 2 — trace показывает, какой tool вернул неожиданный результат и заставил модель переосмыслить план.
- **Почему так дорого?** Trace показывает token count на каждом шаге: где context разросся, какой prompt добавил 4K токенов.
- **Почему такой ответ?** Trace показывает chain-of-thought модели — какие подсказки она себе давала перед финальным ответом. Полезно для debugging'а галлюцинаций.
- **Где fail?** Trace показывает, какой именно шаг в многоэтапной agent-loop упал — без трейса это «session failed» без деталей.

Всё это недоступно через metrics (те агрегаты) и через logs (те без контекста chain). Tracing — единственный сигнал, дающий **причинно-следственную цепочку**.

## GenAI semantic conventions

OpenTelemetry имеет отдельную спецификацию для GenAI-вызовов — [GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). Это стандартные имена span attributes, которые понимают все major observability-vendors.

### Базовый span для LLM call

```
span: chat yandexgpt-4-pro
  name:           "chat yandexgpt-4-pro"
  kind:           CLIENT
  attributes:
    # Идентификация вызова
    gen_ai.system:            "yandex"               # provider
    gen_ai.request.model:     "yandexgpt-4-pro"      # конкретная модель
    gen_ai.operation.name:    "chat"                 # chat / completion / embed

    # Параметры запроса
    gen_ai.request.max_tokens:    2048
    gen_ai.request.temperature:   0.7
    gen_ai.request.top_p:         0.9
    gen_ai.request.stop_sequences: ["\n\nUser:"]

    # Использование токенов (заполняется после ответа)
    gen_ai.usage.input_tokens:     1247
    gen_ai.usage.output_tokens:     834
    gen_ai.usage.cached_tokens:      92   # если поддерживается

    # Идентификатор ответа от provider'а
    gen_ai.response.id:         "rcdb-4f8e-..."
    gen_ai.response.finish_reason:  "stop"  # stop / length / tool_calls / content_filter
```

### Span для tool call

```
span: tool search_docs
  name:           "tool search_docs"
  kind:           INTERNAL
  attributes:
    gen_ai.tool.name:         "search_docs"
    gen_ai.tool.call.id:      "call_abc123"           # из ответа модели
    gen_ai.tool.description:  "Search internal docs"  # опционально

    # Аргументы — сериализованные, без секретов
    gen_ai.tool.input:        '{"query":"...", "limit":5}'

    # Результат
    gen_ai.tool.output:       '{"results":[...]}'     # может быть сокращён
    tool.duration.parse:      0.012                    # секунды на парсинг
    tool.duration.exec:       0.234                    # секунды на execution
```

### Span для agent iteration

```
span: agent_iteration 3
  name:           "agent_iteration 3"
  kind:           INTERNAL
  attributes:
    agent.iteration:           3
    agent.stop_reason:         "tool_calls"            # model wants to call tool
    agent.tokens_accumulated:  2341                    # context size так far
    agent.budget_remaining:    4096                    # tokens left before cap
```

## Полный trace одной session

```
trace: 4f8e-...   (session_id=abc, user=hash_123)
│
├─ span: harness_request                        12.4s total
│  │
│  ├─ span: agent_iteration 1                   1.2s
│  │  ├─ span: chat yandexgpt-4-pro             1.1s
│  │  │   gen_ai.usage.input_tokens=120
│  │  │   gen_ai.usage.output_tokens=80
│  │  │   gen_ai.response.finish_reason=tool_calls
│  │  └─ span: tool search_docs                 0.08s
│  │      tool.input={"query":"harness design"}
│  │      tool.output={"results":[3 items]}
│  │
│  ├─ span: agent_iteration 2                   3.4s
│  │  ├─ span: chat yandexgpt-4-pro             2.8s
│  │  │   gen_ai.usage.input_tokens=487          ← context вырос
│  │  │   gen_ai.usage.output_tokens=140
│  │  │   gen_ai.response.finish_reason=tool_calls
│  │  ├─ span: tool execute_sql                 0.6s
│  │  └─ span: guardrail check                  0.02s
│  │
│  ├─ span: agent_iteration 3                   7.8s
│  │  ├─ span: chat yandexgpt-4-pro             7.6s   ← длинный reasoning
│  │  │   gen_ai.usage.input_tokens=1247
│  │  │   gen_ai.usage.output_tokens=834
│  │  │   gen_ai.response.finish_reason=stop
│  │  └─ (no tool call — финальный ответ)
│  │
│  └─ span: post_process                        0.02s
│      pii_filter.passed=true
│
└─ (trace end)
```

Из этого трейса сразу видно: **3-я итерация заняла 7.6s** и потратила большую часть токенов — модель долго reasoning'ила перед финальным ответом. Если бы latency была проблемой — оптимизировать надо именно шаблон 3-й итерации (например, ограничить `max_tokens` или добавить thinking-budget).

## Context propagation

Одна из главных ценностей OTel — **trace context propagation**. Когда harness вызывает внешний tool (через HTTP), trace context должен передаваться в `traceparent` header:

```
GET /api/search HTTP/1.1
Host: search-service.internal
traceparent: 00-4f8e1234abcdef...-a1b2c3d4ef...-01
                ▲                  ▲
                trace_id           span_id (текущего tool-call span)
```

Это позволяет в Jaeger/Tempo увидеть **сквозной trace** от harness через tool-сервис до DB-запроса внутри него.

**Важно:** traceparent propagation должен быть включён и в outbound HTTP-клиенте harness'а, и в самом tool-сервисе. OTel auto-instrumentation для популярных HTTP-клиентов делает это автоматически; для кастомных — добавьте middleware явно.

## Sampling: какие трейсы сохранять

Трейсы стоят дорого (network + storage). Сохранять 100% в production обычно не нужно. Стратегии:

| Стратегия | Что сохраняет | Когда использовать |
|-----------|--------------|---------------------|
| **`traceidratio` 0.1** | 10% всех запросов (детерминированно по trace_id) | Базовая стратегия для production |
| **`parentbased`** | 10% от корневых + 100% если родитель семплирован | Распределённые системы с несколькими хопами |
| **`always_on` errors** | 100% ошибок + 10% успешных | Рекомендуемая стратегия для harness |
| **Tail sampling** | Решение по итогам трейса (если содержит ошибку / если latency > p99) | Самая гибкая, требует tail-sampling processor в Collector |

Рекомендуемый старт:

```yaml
traces:
  sampler:
    type: parentbased
    parent_sampled:
      type: traceidratio
      ratio: 0.1
    parent_not_sampled:
      type: always_on      # ловим ошибки, у которых root-span уже отмаркирован как error
  tail_sampling:
    decision_wait: 5s
    policies:
      - name: errors
        type: status_code
        status_code: {status_codes: [ERROR]}
      - name: slow
        type: latency
        latency: {threshold_ms: 10000}    # >10s — всегда сохраняем
      - name: sample
        type: probabilistic
        probabilistic: {sampling_percentage: 5}
```

Это даёт: 100% ошибок, 100% медленных (>10s) запросов, 5% остальных. Достаточно для debugging'а и достаточно дёшево для storage.

## Что класть в span attributes (а что не класть)

**✓ Кладите:**

- Идентификаторы: `session_id`, `user_id_hashed` (хеш!), `request_id`.
- Метаданные модели: `gen_ai.request.model`, `gen_ai.request.temperature`, `gen_ai.request.max_tokens`.
- Использование: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`.
- Бизнес-контекст: `task.type`, `tool.name`, `feature.area`.

**✗ Не кладите:**

- Полный prompt или completion (в span attributes). Большой объём, много ПДн. Лучше в отдельный storage с `trace_id` как ключом.
- Секреты: API keys, пароли, токены.
- High-cardinality данные: `user.email`, `session.title` — каждый уникальный value раздувает индексы.
- Сырые tool outputs если они большие (больше 1KB). Сокращайте.

## Стоимость и trade-off'ы

- **Network:** каждый span — это ~200–500 bytes при экспорте. Session с 20 итерациями и 5 tool calls на итерацию = ~100 spans = ~30KB. На 1000 sessions/day это ~30MB/day только traces.
- **Storage:** Tempo/Jaeger держат данные 7 дней по умолчанию. Увеличение retention до 30 дней удваивает стоимость storage.
- **Latency overhead:** каждый span создаётся за ~10–50 µs. На hot path с тысячами spans в секунду это складывается.
- **Cost:** observability-vendors берут за GB ingested. Traces дороже metrics. Сэмплирование — главный рычаг.

Бюджет правила: **traces должны стоить не больше 5–10% от общей стоимости harness'а** (включая model inference). Если дороже — пересмотрите sampling.

## Чек-лист

- [ ] Все LLM-вызовы обёрнуты в span с GenAI semantic conventions.
- [ ] Все tool calls имеют span с `gen_ai.tool.name` и `gen_ai.tool.input` (без секретов).
- [ ] Agent-loop итерации — отдельные span'ы с `agent.iteration` и `agent.tokens_accumulated`.
- [ ] Trace context propagation включён для outbound HTTP (через `traceparent` header).
- [ ] Sampling: errors 100%, slow requests 100%, остальные 5–10%.
- [ ] Retention: traces 7 дней (production), 30 дней (для active debugging period).
- [ ] Cost budget: traces ≤10% от общего cost harness'а.
- [ ] Секретов и ПДн в span attributes нет (только хеши и метаданные).

## Что читать дальше

- [Observability](/guide/observability) — обзор всех сигналов.
- [Harness Metrics](/guide/harness-metrics) — метрики, которые дополняют traces.
- [Error Handling](/guide/error-handling) — какие ошибки как классифицировать в span status.
- [OpenTelemetry GenAI spec](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — официальный стандарт.
