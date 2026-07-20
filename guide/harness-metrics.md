---
author: Harness Engineering Guide (RU)
title: "Harness Metrics: RED для LLM-систем"
section: practice
description: "Какие метрики собирать в production harness: RED-методология адаптированная под LLM, naming conventions, гистограммы для latency, токен-скоринг, cost-as-first-class-metric. Чек-лист метрик, которые реально нужны."
category: Practice
date: "2026-07-23"
---

# Harness Metrics: RED для LLM-систем

> **Главный инсайт:** Классическая RED (Rate, Errors, Duration) работает для harness только если расширить её двумя измерениями: **Tokens** (потребление ресурсов модели) и **Cost** (деньги). Без них вы знаете «сколько и как быстро», но не знаете «дорого ли» и «не превышен ли budget».

## Почему RED недостаточен

RED описывает сервис с точки зрения клиентских запросов: сколько их пришло (Rate), какая доля завершилась ошибкой (Errors), сколько времени занял ответ (Duration). Для HTTP-эндпоинта этого хватает.

LLM-harness добавляет два измерения, без которых метрики превращаются в шум:

1. **Tokens.** Каждый запрос имеет разный «вес» — короткий prompt + длинный ответ стоит иначе, чем длинный prompt + короткий. Считать только «requests per second» — значит сравниватьSession с 10 итерациями агента и Session с одним вызовом модели.
2. **Cost.** Если 1% запросов стоит в 100 раз дороже остальных (длинный контекст + reasoning), общий «average cost per request» скрывает хвост. Cost должен быть гистограммой, не средней.

Итоговая методология — **REDCoT** (Rate, Errors, Duration, Cost, Tokens). Не勃 emerging стандарт, но рабочая мнемоника.

## Канонический набор метрик

### 1. Request rate (counter)

```
# HELP harness_requests_total Total harness requests by outcome
# TYPE harness_requests_total counter
harness_requests_total{status="success"}  42891
harness_requests_total{status="error"}     127
harness_requests_total{status="refusal"}   43
harness_requests_total{status="timeout"}   12
```

**Важно:** `status` — не HTTP-код, а **семантический исход** harness-вызова:

| `status` | Что значит | Пример |
|----------|-----------|--------|
| `success` | Модель ответила, harness достиг цели | Tool выполнен, ответ релевантный |
| `error` | Сбой infra / API / tool | HTTP 5xx, tool timeout, JSON parse fail |
| `refusal` | Модель отказалась отвечать | «Я не могу помочь с этим» |
| `timeout` | Превышен общий budget session | 30s wall-clock |
| `cancelled` | Пользователь прервал | Кнопка Stop в UI |

HTTP 200 + refusal всё ещё частый production-баг, который без этой метрики невидим.

### 2. Request duration (histogram)

```
# HELP harness_request_duration_seconds Wall-clock harness request duration
# TYPE harness_request_duration_seconds histogram
harness_request_duration_seconds_bucket{le="0.5"}  8123
harness_request_duration_seconds_bucket{le="1"}   21034
harness_request_duration_seconds_bucket{le="2"}   34901
harness_request_duration_seconds_bucket{le="5"}   41877
harness_request_duration_seconds_bucket{le="10"}  42512
harness_request_duration_seconds_bucket{le="30"}  42879
harness_request_duration_seconds_bucket{le="60"}  42891
harness_request_duration_seconds_bucket{le="+Inf"} 42918
```

**Buckets для harness — не стандартные HTTP buckets.** LLM-вызовы имеют бимодальное распределение: быстрый ответ (1–3s) и длинный reasoning (15–60s). Стандартные Prometheus buckets (0.005, 0.01, 0.025...) бесполезны; нужны пороги, отражающие реальный UX:

```yaml
buckets_seconds: [0.5, 1, 2, 5, 10, 30, 60, 120, 300]
```

**Метрики:** p50 (типичный случай), p95 (что видит большинство), p99 (tail latency — главный SLO). p99 в harness нормально держать в районе 20–30s для reasoning-задач; 60+ секунд уже подозрительно.

### 3. Errors по классам (counter, multi-label)

```
# HELP harness_errors_total Errors by class
# TYPE harness_errors_total counter
harness_errors_total{class="model_api"}      23    # 5xx от provider
harness_errors_total{class="model_rate"}     87    # 429
harness_errors_total{class="tool_exec"}      12    # tool упал
harness_errors_total{class="tool_timeout"}    8    # tool превысил SLA
harness_errors_total{class="guardrail"}      43    # заблокирован
harness_errors_total{class="context_length"} 19    # input > max_tokens
harness_errors_total{class="json_parse"}      5    # модель вернула битый JSON
harness_errors_total{class="budget"}          2    # session превысила token budget
```

**Зачем классификация:** общий «error rate» бесполезен для debugging'а. Если error rate вырос — нужно знать, из-за чего. `model_rate` требует throttle'а; `tool_exec` — чинить tool; `json_parse` — усилить prompt template или парсер.

### 4. Token consumption (counter, multi-dim)

```
# HELP harness_tokens_consumed_total Tokens consumed by type and policy
# TYPE harness_tokens_consumed_total counter
harness_tokens_consumed_total{kind="prompt",  policy="paid"}    128_492_341
harness_tokens_consumed_total{kind="prompt",  policy="free"}     12_039_882
harness_tokens_consumed_total{kind="output",  policy="paid"}    49_234_001
harness_tokens_consumed_total{kind="output",  policy="free"}     3_921_004
harness_tokens_consumed_total{kind="cached",  policy="paid"}     8_392_111
```

**Метка `kind`:**

- `prompt` — входящие токены (включая context, memory, tool results).
- `output` — сгенерированные моделью.
- `cached` — попадания в prompt cache (Anthropic / YandexGPT), считается отдельно для оценки cache effectiveness.

**Метка `policy`:**

- `paid` — тарифицируемые токены.
- `free` — бесплатные (fine-tune evaluation tokens, internal test traffic).

Без разделения `paid`/`free` внутренний R&D-трафик исказит production-метрики.

### 5. Cost (counter + histogram)

```
# HELP harness_request_cost_usd_total Estimated USD cost of harness requests
# TYPE harness_request_cost_usd_total counter
harness_request_cost_usd_total{model="yandexgpt-4-pro"} 128.42
harness_request_cost_usd_total{model="gigachat-max"}     42.91
harness_request_cost_usd_total{model="local-vllm"}        0.00  # inference amortized

# HELP harness_request_cost_usd Distribution of per-request cost
# TYPE harness_request_cost_usd histogram
harness_request_cost_usd_bucket{le="0.001"}  38291
harness_request_cost_usd_bucket{le="0.005"}  41123
harness_request_cost_usd_bucket{le="0.01"}   42101
harness_request_cost_usd_bucket{le="0.05"}   42701
harness_request_cost_usd_bucket{le="0.1"}    42855
harness_request_cost_usd_bucket{le="0.5"}    42889
harness_request_cost_usd_bucket{le="+Inf"}   42918
```

**Для локальных моделей** (vLLM, Ollama) cost = 0 на момент вызова, но реальная стоимость — amortized GPU time. Считайте отдельно через capacity planning, не на hot-path.

### 6. LLM latency (histogram, per-model)

```
harness_llm_latency_seconds{model,provider}
```

Отдельная метрика для latency чистого LLM-вызова (без tool execution, без guardrails). Помогает отделить «модель долго думает» от «наш код долго выполняется».

### 7. Tool calls (counter)

```
harness_tool_calls_total{name="search_docs",   status="success"} 3491
harness_tool_calls_total{name="search_docs",   status="error"}     12
harness_tool_calls_total{name="execute_sql",   status="success"}  892
harness_tool_calls_total{name="execute_sql",   status="timeout"}    8
harness_tool_calls_total{name="send_email",    status="success"}  234
harness_tool_calls_total{name="send_email",    status="blocked"}    3   # guardrail
```

Самые важные tool'ы по `error`+`timeout` — кандидаты на retry-стратегию или новый SLA.

### 8. Guardrails tripped (counter)

```
harness_guardrails_tripped_total{rule="pii_filter"}        43
harness_guardrails_tripped_total{rule="prompt_injection"}  12
harness_guardrails_tripped_total{rule="jailbreak"}          3
harness_guardrails_tripped_total{rule="topic_block"}       29
```

Если `prompt_injection` растёт — возможно, вас атакуют. См. [Incident Runbook](/guide/incident-runbook).

### 9. Agent-loop iterations (histogram)

```
# HELP harness_agent_iterations_per_session Distribution of iterations per session
harness_agent_iterations_per_session_bucket{le="1"}  23891   # one-shot
harness_agent_iterations_per_session_bucket{le="3"}  34901   # typical
harness_agent_iterations_per_session_bucket{le="5"}  39123
harness_agent_iterations_per_session_bucket{le="10"} 42101   # complex task
harness_agent_iterations_per_session_bucket{le="20"} 42700   # runaway?
harness_agent_iterations_per_session_bucket{le="+Inf"} 42918
```

Sessions с >20 итераций — подозрительны: либо сложная задача, либо harness зациклился. Зашивайте hard cap в [Sandbox](/guide/sandbox).

## Naming conventions

Чтобы метрики из разных harness-компонентов складывались в единую картину:

- **Prefix:** `harness_*` для app-level, `harness_tool_*` для tool-вызовов, `harness_llm_*` для provider-вызовов.
- **Suffixes:** `_total` (counter), `_seconds` (histogram of duration), `_bytes` (size), `_count`/`_sum` (histogram aggregates).
- **Labels:** snake_case, короткие значения. Не используйте UUID/high-cardinality данные (user_id, session_id) — это убьёт TSDB.
- **Units в имени, не в label.** `harness_request_duration_seconds`, не `harness_request_duration{unit="seconds"}`.

> Подробнее — в [Prometheus naming conventions](https://prometheus.io/docs/practices/naming/).

## Что НЕ измерять

- **Per-user token usage как метрику.** High cardinality убьёт TSDB. Логируйте per-user в logs/OLAP, не в Prometheus.
- **Prompt content.** Это данные, не метрика. См. [Observability](/guide/observability#стоимость-observability-и-trade-off-ы) про privacy.
- **Model scores per request.** Eval-метрики — отдельный pipeline, не hot-path (см. [Eval Infrastructure](/guide/eval-infrastructure)).
- **Latency в микросекундах.** LLM-вызовы — это секунды, не микросекунды. Точность выше ms избыточна.

## Чек-лист

- [ ] Все counters имеют метку `status` (или эквивалент), а не просто `total`.
- [ ] Duration-гистограммы используют harness-бакеты `[0.5, 1, 2, 5, 10, 30, 60, 120, 300]`, не дефолт Prometheus.
- [ ] Token counter разделён по `kind` (prompt/output/cached) и `policy` (paid/free).
- [ ] Cost считается и как counter (overall), и как histogram (per-request distribution).
- [ ] LLM latency отделена от harness request duration.
- [ ] Guardrails tripped — отдельная метрика, не смешана с errors.
- [ ] Agent-loop iterations имеют hard cap (защита от runaway).

## Что читать дальше

- [Observability](/guide/observability) — общий framework, как metrics вписываются в картину.
- [LLM Tracing](/guide/llm-tracing) — для drill-down из metrics в конкретные span'ы.
- [Alerting и SLO](/guide/alerting-and-slo) — какие метрики становятся SLO.
- [Error Handling](/guide/error-handling) — классификация ошибок, лежащая в основе `harness_errors_total{class}`.
