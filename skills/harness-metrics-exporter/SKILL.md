---
name: harness-metrics-exporter
description: Конвертер JSON-lines логов harness в Prometheus exposition format. Парсит structured logs (одна запись на строку, формат описан в SKILL.md), агрегирует по окну наблюдения (последние N минут или весь файл) и выводит канонические метрики из статьи [Harness Metrics](/guide/harness-metrics): harness_requests_total, harness_errors_total, harness_tokens_consumed_total, harness_request_duration_seconds (histogram), harness_llm_latency_seconds, harness_tool_calls_total, harness_guardrails_tripped_total, harness_agent_iterations_per_session, harness_request_cost_usd. Готов для node_exporter textfile collector (пишет в .prom файл). Только Python stdlib — никаких внешних зависимостей, работает в air-gapped.
---

# harness-metrics-exporter — логи harness → Prometheus

Превращает structured JSON-логи harness (одна запись на строку) в готовые Prometheus-метрики. Применяется, когда нет возможности внедрить full OpenTelemetry pipeline — например, в on-prem инсталляциях с минимальным observability-стеком (node_exporter + Prometheus + Grafana).

## Когда использовать

- **On-prem / air-gapped** — нет внешнего SaaS-вендора, нужно собрать базовую observability из логов
- **Быстрый старт observability** — логи уже есть, метрики нужны вчера
- **Аудит истории** — прогнать логи за прошлый месяц, получить baseline для SLO
- **Траблшутинг** — быстро конвертировать логи инцидента в метрики для RCA
- ** bridge к full OTel pipeline** — пока внедряете, лог→Prometheus закрывает пробел

## Когда НЕ использовать

- Уже есть Prometheus client library в приложении (метрики экспортируются напрямую)
- Логи не structured (простой текст, разные форматы) — сначала надо их нормализовать
- High-cardinality use-case (per-user метрики) — это задача OLAP, не Prometheus

## Формат входных логов

Скрипт ожидает **JSON Lines** (одна запись на строку), с полями:

```json
{
  "ts": "2026-07-20T10:23:00Z",
  "trace_id": "4f8eabc123",
  "session_id": "sess_xyz789",
  "user_id_hashed": "h_a1b2c3",
  "status": "success",
  "duration_s": 3.42,
  "model": "yandexgpt-4-pro",
  "provider": "yandex",
  "tokens": {
    "prompt": 1247,
    "output": 834,
    "cached": 0
  },
  "cost_usd": 0.0234,
  "iterations": 3,
  "llm_latency_s": 2.91,
  "tool_calls": [
    {"name": "search_docs", "status": "success"}
  ],
  "guardrails_tripped": ["pii_filter"],
  "error_class": null
}
```

**Обязательные поля:** `ts`, `status` (один из `success`/`error`/`refusal`/`timeout`/`cancelled`).
**Опциональные:** остальные. Отсутствующие поля заменяются дефолтами (0 / пустой список / `unknown`).

## Запуск

```bash
# Базовый запуск — весь файл, вывод в stdout
python3 skills/harness-metrics-exporter/scripts/export.py \
    --input /var/log/harness/2026-07-20.jsonl

# Только последние 5 минут лога (для node_exporter textfile collector)
python3 skills/harness-metrics-exporter/scripts/export.py \
    --input /var/log/harness/current.jsonl \
    --window-minutes 5 \
    --output /var/lib/node_exporter/textfile/harness.prom

# Через cron — каждые 30 секунд
* * * * *  python3 /opt/skills/harness-metrics-exporter/scripts/export.py \
    --input /var/log/harness/current.jsonl \
    --window-minutes 1 \
    --output /var/lib/node_exporter/textfile/harness.prom
* * * * * sleep 30; python3 /opt/skills/harness-metrics-exporter/scripts/export.py \
    --input /var/log/harness/current.jsonl \
    --window-minutes 1 \
    --output /var/lib/node_exporter/textfile/harness.prom
```

## Сгенерированные метрики

```
# HELP harness_requests_total Total harness requests by outcome
# TYPE harness_requests_total counter
harness_requests_total{status="success"}  42891
harness_requests_total{status="error"}     127
harness_requests_total{status="refusal"}   43
harness_requests_total{status="timeout"}   12
harness_requests_total{status="cancelled"} 8

# HELP harness_errors_total Errors by class
# TYPE harness_errors_total counter
harness_errors_total{class="model_api"}      23
harness_errors_total{class="model_rate"}     87
harness_errors_total{class="tool_exec"}      12
harness_errors_total{class="tool_timeout"}    8
harness_errors_total{class="guardrail"}      43
harness_errors_total{class="context_length"} 19
harness_errors_total{class="json_parse"}      5
harness_errors_total{class="budget"}          2

# HELP harness_tokens_consumed_total Tokens consumed by kind and policy
# TYPE harness_tokens_consumed_total counter
harness_tokens_consumed_total{kind="prompt",policy="paid"} 128492341
harness_tokens_consumed_total{kind="output",policy="paid"} 49234001
harness_tokens_consumed_total{kind="cached",policy="paid"} 8392111

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
harness_request_duration_seconds_sum 78342.91
harness_request_duration_seconds_count 42918

# HELP harness_agent_iterations_per_session Distribution of iterations per session
# TYPE harness_agent_iterations_per_session histogram
harness_agent_iterations_per_session_bucket{le="1"}  23891
harness_agent_iterations_per_session_bucket{le="3"}  34901
harness_agent_iterations_per_session_bucket{le="5"}  39123
harness_agent_iterations_per_session_bucket{le="10"} 42101
harness_agent_iterations_per_session_bucket{le="20"} 42700
harness_agent_iterations_per_session_bucket{le="+Inf"} 42918
harness_agent_iterations_per_session_count 42918
harness_agent_iterations_per_session_sum 134891

# HELP harness_request_cost_usd Total estimated USD cost
# TYPE harness_request_cost_usd counter
harness_request_cost_usd 171.42

# HELP harness_tool_calls_total Tool calls by name and status
# TYPE harness_tool_calls_total counter
harness_tool_calls_total{name="search_docs",status="success"} 3491
harness_tool_calls_total{name="search_docs",status="error"}     12
harness_tool_calls_total{name="execute_sql",status="success"}  892
harness_tool_calls_total{name="execute_sql",status="timeout"}    8

# HELP harness_guardrails_tripped_total Guardrail hits by rule
# TYPE harness_guardrails_tripped_total counter
harness_guardrails_tripped_total{rule="pii_filter"}        43
harness_guardrails_tripped_total{rule="prompt_injection"}  12
```

## Bucket'ы

Гистограммы используют harness-специфичные бакеты (см. [Harness Metrics](/guide/harness-metrics#2-request-duration-histogram)):

- **`harness_request_duration_seconds`**: `[0.5, 1, 2, 5, 10, 30, 60, 120, 300]` — бимодальное распределение LLM-ответов.
- **`harness_agent_iterations_per_session`**: `[1, 3, 5, 10, 20, 50]` — one-shot / typical / complex / suspicious.
- **`harness_llm_latency_seconds`**: `[0.1, 0.5, 1, 2, 5, 10, 30]` — чистая LLM latency без tool execution.

Если нужны другие бакеты — правьте константу `BUCKETS` в начале скрипта.

## Price policy

По умолчанию все токены считаются `policy="paid"`. Если лог содержит поле `policy` (например, для internal R&D traffic), оно используется.

## Пример интеграции с node_exporter

`/etc/prometheus/node_exporter.conf`:

```yaml
collectors:
  textfile:
    directory: /var/lib/node_exporter/textfile
```

Cron каждые 30 секунд обновляет `harness.prom`. Prometheus скрейпит `node_exporter`, видит метрики `harness_*`. Готово.

## Адаптация

- **Длинные файлы** (>1GB): скрипт стримит построчно, не загружая весь файл в память. O(1) RAM.
- **Multiple файлов**: передайте несколько `--input` (или склейте через `cat`).
- **Real-time tail**: используйте `tail -F file.jsonl | python3 export.py --input -` (с pipe).
- **Кастомные модели**: метка `model` берётся из поля `model` лога; если поле отсутствует, ставится `unknown`.

## Антипаттерны

- **Ложить user_id в метки** — убьёт TSDB. Скрипт намеренно игнорирует `user_id_hashed` для меток.
- **Ложить trace_id в метки** — то же самое. `trace_id` используется только в логах, не в метриках.
- **Считать averages вместо histograms** — average latency скрывает хвост. Скрипт всегда строит гистограммы для duration / iterations.
- **Не фильтровать window** — метрики на страницах за весь день будут «дрейфовать» и давать alert storms. Для real-time всегда `--window-minutes N`.

## Связанные материалы

- [Harness Metrics](/guide/harness-metrics) — какие метрики и почему именно такие.
- [Observability](/guide/observability) — общий контекст четырёх сигналов.
- [Alerting и SLO](/guide/alerting-and-slo) — что делать с этими метриками дальше.
