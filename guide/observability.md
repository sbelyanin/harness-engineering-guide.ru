---
author: Harness Engineering Guide (RU)
title: "Observability для Harness: три сигнала + эвалюации"
section: core-concepts
description: "Почему классического мониторинга недостаточно для LLM-систем, какие сигналы собирать в harness, и как связать observability с eval infrastructure. Практические рецепты для production-readiness."
category: Core Concepts
date: "2026-07-23"
---

# Observability для Harness: три сигнала + эвалюации

> **Главный инсайт:** Классический мониторинг (RED / USE / four golden signals) создавался для детерминированных сервисов. LLM-система принципиально недетерминирована: один и тот же запрос может вернуть полезный ответ, галлюцинацию или refusal — и все три имеют HTTP 200. Без специализированной observability вы узнаете о проблеме от пользователя, через несколько дней после инцидента.

## Почему обычный мониторинг не работает

Для обычного HTTP-сервиса успех = `2xx`, ошибка = `5xx`. Latency и error rate — почти всё, что нужно знать.

Harness ломает эту модель на нескольких уровнях сразу:

- **Коды лгут.** LLM возвращает 200 OK с refusal'ом («Я не могу помочь с этим»), с галлюцинацией или с утечкой prompt'а. HTTP-статус ничего не говорит о качестве ответа.
- **Latency имеет длинный хвост.** Один запрос к модели — 800 ms, другой — 25 секунд (рассуждение через tool-calls в несколько итераций). p50 бесполезен, нужен p99 и tail latency.
- **Cost — первый класс.** Каждый запрос стоит денег; session без лимита может сжечь дневной бюджет за один run. Cost должен быть метрикой первого класса, а не财务ным отчётом раз в месяц.
- **Drift невидим без evals.** Model vendor молча обновил веса — ответы стали чуть хуже. Без автоматических эвалюаций вы заметите это через NPS, через неделю.
- **Context растёт.** У обычного сервиса вход фиксированный; у harness'а контекст нарастает по ходу session (memory + tool outputs + clarifications). Потребление token'ов растёт нелинейно.

Вывод: harness требует **четырёх сигналов** вместо классических трёх.

## Четыре сигнала harness observability

| Сигнал | Что отвечает | Классический аналог |
|--------|--------------|---------------------|
| **Metrics** | Что происходит в среднем? | Prometheus, RED |
| **Logs** | Что произошло в конкретном запросе? | structured logging, ELK |
| **Traces** | Где время и где ошибка внутри agent-loop? | OpenTelemetry, Jaeger |
| **Evaluations** | Насколько хорошо модель отвечает? | SLO на качество — уникально для LLM |

Первые три — стандартная observability. Четвёртый — единственный способ понять, что модель не просто «работает», а «работает хорошо».

> Подробнее о каждом сигнале — в отдельных статьях: [Harness Metrics](/guide/harness-metrics), [LLM Tracing](/guide/llm-tracing), [Eval Infrastructure](/guide/eval-infrastructure).

## Архитектура observability-стека

```
┌───────────────────── HARNESS (приложение) ─────────────────────┐
│                                                                 │
│   agent-loop ──→ LLM call ──→ tool call ──→ guardrail check     │
│        │            │             │              │              │
│        ▼            ▼             ▼              ▼              │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              instrumentation layer (SDK)                │   │
│   │  • OpenTelemetry spans (GenAI semconv)                  │   │
│   │  • structured JSON logs (correlated via trace_id)       │   │
│   │  • Prometheus counters/histograms                       │   │
│   │  • eval hooks (offline + online)                        │   │
│   └─────────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
       ┌────────────────────┼────────────────────┐
       ▼                    ▼                    ▼
┌─────────────┐    ┌────────────────┐    ┌───────────────────┐
│  Metrics    │    │     Logs       │    │      Traces       │
│             │    │                │    │                   │
│ Prometheus  │    │  Loki / ELK    │    │  Tempo / Jaeger   │
│  + Grafana  │    │  (retention    │    │  (sampling:       │
│  + Alerting │    │   30-90 дней)  │    │   head 10%,       │
│             │    │                │    │   errors 100%)    │
└──────┬──────┘    └────────┬───────┘    └─────────┬─────────┘
       │                    │                      │
       └────────────────────┼──────────────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │      Evals       │
                  │                  │
                  │  offline: nightly│
                  │   regression     │
                  │  online: sampled │
                  │   real traffic   │
                  │  → eval-store    │
                  └──────────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │   Alerting +     │
                  │   oncall routing │
                  │   (Slack/Pager)  │
                  └──────────────────┘
```

**Ключевые свойства:**

- **Единый `trace_id`** проходит через все четыре сигнала — log entry можно найти по trace, метрику можно разрезать по trace_id при debug'е.
- **Evals отдельным потоком** — не на hot-path ответа. Offline гоняется по ночам на корпусе репрезентативных prompt'ов; online — на сэмплированной доле реальных запросов (1–5%).
- **Sampling разный для разных сигналов.** Метрики — 100% (дёшевы). Логи — обычно 100%, но понижение до 10% для успешных (без error). Traces — head sampling 5–10% + 100% для ошибочных.

## Минимальный production-набор

Если ресурсов мало, начните с этого:

```yaml
# Минимальный observability-стек для single-node harness
metrics:
  prometheus: enabled
  default_retention: 15d
  key_metrics:
    - harness_requests_total{status}              # counter
    - harness_request_duration_seconds            # histogram, buckets по p99
    - harness_tokens_consumed_total{type,policy}  # counter (prompt/completion, paid/free)
    - harness_llm_latency_seconds{model,provider} # histogram
    - harness_tool_calls_total{name,status}       # counter
    - harness_guardrails_tripped_total{rule}      # counter

logs:
  format: json
  fields_mandatory: [trace_id, session_id, user_id_hashed, model, tokens_used]
  retention: 30d

traces:
  opentelemetry: enabled
  sampler: traceidratio 0.1        # 10% здоровых
  sampler_errors: always_on        # 100% ошибок
  exporter: otlp → tempo/jaeger
  retention: 7d

evals:
  offline_schedule: "0 3 * * *"    # nightly
  offline_dataset: ./eval-corpus/
  online_sample_rate: 0.02         # 2% реального трафика
```

Этого достаточно, чтобы:

- Заметить регрессию latency или error rate за минуты (metrics + alerting).
- Найти конкретный сбойный запрос за секунды (logs по trace_id из alert'а).
- Понять, где именно в agent-loop произошла задержка (traces).
- Поймать тихий дрейф модели за сутки-двое (offline evals vs. baseline).

## Стоимость observability и trade-off'ы

Observability — не бесплатная опция. Ошибки на этом уровне стоят дорого:

- **Логи с полным prompt/response** могут содержать ПДн или секреты. В РФ-инсталляциях под 152-ФЗ такие логи попадают в perimeter ПДн и требуют отдельной защиты. Решение: логировать хеши prompt'а + метаданные, полный payload — отдельно, с short TTL.
- **Tracing добавляет latency.** Каждый span — это несколько µs на создание + сериализацию. На горячих путях используйте sampling, не сохраняйте трейсы для каждого запроса.
- **Online evals стоят денег.** Если eval'ить каждый 10-й запрос через LLM-as-judge, вы удваиваете cost per session. Сэмлируйте 1–2% и используйте более дешёвые методы (classifier / regex) где возможно.
- **Storage growing.** Traces и eval-корпуса растут быстро. Определите retention policy явно: traces 7 дней, logs 30 дней, evals навсегда (но в агрегированном виде).

> Подробнее про стоимость и cost-optimization — в [Cyrillic Tokenization](/guide/cyrillic-tokenization) и [Russian LLM в Harness](/guide/russian-llm-harness).

## Связь с eval infrastructure

Evals — не послеthought, а четвёртый сигнал observability. Их место в общем стеке:

- **Offline evals** — корпус репрезентативных prompt'ов, гоняется регулярно (nightly / pre-deploy). Ловит регрессию модели или prompt template'а до того, как она дойдёт до production.
- **Online evals** — сэмплированная доля реального трафика оценивается автоматически (LLM-as-judge, classifier, regex rules). Ловит дрейф реального распределения запросов.
- **Shadow evals** — перед deploy'ом новой версии harness'а прогоняют корпус через новую и старую версию, сравнивают метрики. Decision gate для релиза.

> Подробнее — в [Eval Infrastructure](/guide/eval-infrastructure) и [Eval Awareness](/guide/eval-awareness).

## Чек-лист production-ready observability

Перед тем как назвать harness «production-ready», прогоните по чек-листу:

- [ ] **Metrics.** Есть `harness_requests_total`, `harness_request_duration_seconds` (histogram), `harness_tokens_consumed_total` (с меткой policy), `harness_llm_latency_seconds` (с меткой model).
- [ ] **Logs.** Structured JSON, обязательные поля `trace_id` + `session_id` + `tokens_used`. Code-блоки и секреты redacted.
- [ ] **Traces.** OpenTelemetry с GenAI semantic conventions. Sampling: head 5–10%, errors 100%. Trace context propagated через границы tool-calls.
- [ ] **Evals.** Offline корпус с baseline метриками. Online sampling 1–5% реального трафика. Алерт при падении ниже baseline.
- [ ] **Alerting.** SLO определены (success rate, latency p99, cost per session). Multi-window multi-burn-rate alerts. Маршрутизация в oncall.
- [ ] **Dashboards.** Grafana (или аналог): overall health, per-model breakdown, top tool errors, token/cost trend, eval pass rate.
- [ ] **Runbooks.** На каждый критический алерт — runbook с шагами diagnosis + remediation.
- [ ] **Retention.** Метрики 15–90 дней, логи 30 дней, трейсы 7 дней, эвалюации — навсегда (агрегированные).
- [ ] **Privacy.** ПДн в логах — хеши или pseudonymization, не plaintext. Соответствие 152-ФЗ для РФ-инсталляций.
- [ ] **Cost budget.** Observability добавляет 5–15% к cost per session; определите потолок явно.

## Что читать дальше

- [Harness Metrics](/guide/harness-metrics) — конкретные метрики, naming conventions, гистограммы.
- [LLM Tracing](/guide/llm-tracing) — OpenTelemetry GenAI semantic conventions.
- [Alerting и SLO](/guide/alerting-and-slo) — multi-window multi-burn-rate, error budget.
- [Incident Runbook](/guide/incident-runbook) — типовые инциденты и postmortem template.
- [Eval Infrastructure](/guide/eval-infrastructure) — четвёртый сигнал подробно.
- [Error Handling](/guide/error-handling) — классификация ошибок и retry-стратегии.
