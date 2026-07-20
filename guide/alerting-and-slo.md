---
author: Harness Engineering Guide (RU)
title: "Alerting и SLO: error budget для Harness"
section: practice
description: "SLO для LLM-систем: что обещать пользователям (success rate, latency p99, cost per session), multi-window multi-burn-rate alerts, error budget как механизм принятия product-решений, oncall routing под 152-ФЗ."
category: Practice
date: "2026-07-23"
---

# Alerting и SLO: error budget для Harness

> **Главный инсайт:** SLO в harness — это не «promise 99.9% uptime», а явный договор о том, что считать «работает хорошо». Без SLO любая неидеальная метрика порождает алерт; с SLO — вы получаете алерт только когда **реально начали жечь user trust**, и у вас есть явный budget на рискованные деплои.

## SLO vs SLA vs SLI — коротко

- **SLI** (Service Level Indicator) — измеримая метрика: «success rate за последние 5 минут», «p99 latency за час».
- **SLO** (Service Level Objective) — цель: «success rate ≥99% за 28 дней».
- **SLA** (Service Level Agreement) — юридическое обязательство перед клиентом: «если success rate <99% за месяц — возврат 10% оплаты».

В этой статье — про SLI и SLO. SLA — отдельная история про юристов и деньги.

## Что считать SLI в harness

### 1. Success rate

```
SLI = harness_requests_total{status="success"} 
      / harness_requests_total (без cancelled)
```

**Важно:** что считать `success`? Не HTTP 200, а семантический исход (см. [Harness Metrics](/guide/harness-metrics#1-request-rate-counter)). `refusal` — это не success (пользователь не получил ответ) и не error (система работает как задумано). Решение зависит от product-контекста:

- Если harness — публичный чат-бот, `refusal` ∈ не-success (плохой UX).
- Если harness — internal code assistant с guardrails, `refusal` ∈ success (сработала защита).

Зафиксируйте явно в SLO-документе.

### 2. Latency p99

```
SLI = histogram_quantile(0.99, rate(harness_request_duration_seconds_bucket[5m]))
```

LLM-системы имеют широкий спектр latency. Один SLO на p99 часто бесполезен — слишком разные сценарии. Разделяйте:

- **One-shot chat**: p99 ≤ 5s
- **Tool-using agent**: p99 ≤ 30s
- **Multi-step reasoning**: p99 ≤ 60s (явно задокументировать как «медленный класс»)

Если смешать всё в одну кучу, p99 получится 90s, и 99% one-shot запросов будут считаться «уложились», хотя реальный UX сломан.

### 3. Cost per session

```
SLI = sum(harness_request_cost_usd_total) / count(distinct session_id)
```

Cost — первый класс для harness. SLO на cost ставит верхней границей «одна сессия не должна стоить больше $X в среднем». Превышение — incident, даже если latency и success rate в норме.

### 4. Eval pass rate

```
SLI = count(evals with score > threshold) / total evals (rolling 24h)
```

Online evals (см. [Observability](/guide/observability#связь-с-eval-infrastructure)) — единственный SLI, который ловит **качество ответов**, а не технические характеристики.

## Какие SLO ставить

Стартовые значения для production harness (подкорректируйте под свой product):

| SLI | SLO target | Window | Что значит |
|-----|-----------|--------|------------|
| Success rate | ≥99% | 28 days | ≤1 из 100 запросов падает по техническим причинам |
| Latency p99 (chat) | ≤5s | 28 days | 99% быстрых запросов укладываются в 5 секунд |
| Latency p99 (agent) | ≤30s | 28 days | 99% сложных agent-задач укладываются в 30 секунд |
| Cost per session | ≤$0.50 | 7 days | Средняя сессия дешевле полдоллара |
| Eval pass rate | ≥85% | 7 days | Не менее 85% эвалюаций проходят baseline |

**Бюджет 99% за 28 дней = 7.2 часа даунтайма в квартал.** Это много. Для public-facing продукта обычно начинают с **99% за 28 days** и постепенно ужесточают.

## Error budget

Error budget — главный продукт-менеджерский инструмент SLO. Если SLO = 99% success за 28 дней, **budget = 1% неудач**. Этот budget — ваш «сколько ещё можно ломать prod».

```
SLO target:       99%
Window:           28 days
Error budget:     1% × 28d = 6.72 hours of errors allowed

Текущий burn rate за час: 0.5%
Остаток error budget:     40%
```

Использование error budget'а:

- **Budget > 50%** — можно деплоить рискованные изменения, экспериментировать.
- **Budget 25–50%** — только проверенные изменения, с feature flags.
- **Budget < 25%** — freeze рискованных деплоев, только bugfixes.
- **Budget ≤ 0** — уведомить product/stakeholders, freeze deploys до восстановления.

Это снимает бесконечные споры «можно ли деплоить в пятницу». Если budget позволяет — можно. Если нет — нельзя.

## Multi-window multi-burn-rate alerts

Главное правило алертинга: **алерт должен срабатывать, когда вы быстро жжёте budget**. Не при каждой ошибке, не при превышении порога — а при ускорении burn rate.

Стандартный паттерн — multi-window multi-burn-rate (см. [Google SRE Workbook](https://sre.google/workbook/alerting-on-slos/)):

| Window | Burn rate threshold | Action |
|--------|---------------------|--------|
| 5m + 1h | 14.4× нормальный | Page oncall (быстрый, важный) |
| 30m + 6h | 6× нормальный | Page oncall (средний) |
| 2h + 1d | 3× нормальный | Slack-уведомление (slow burn) |
| 6h + 3d | 1× нормальный | Weekly review (тренд) |

«Multi-window» означает: **оба** короткое и длинное окно должны превысить threshold. Это убирает false positive'ы от кратковременных всплесков.

### Пример alert правила (Prometheus)

```yaml
groups:
  - name: harness_slo
    rules:
      # Page: 14.4× burn rate (5m + 1h)
      - alert: HarnessHighBurnRate
        expr: |
          (
            sum(rate(harness_requests_total{status!="success"}[5m]))
            / sum(rate(harness_requests_total[5m]))
          ) > 0.144
          and
          (
            sum(rate(harness_requests_total{status!="success"}[1h]))
            / sum(rate(harness_requests_total[1h]))
          ) > 0.144
        for: 2m
        labels: {severity: page}
        annotations:
          summary: "Harness burning error budget fast (14.4× over 5m+1h)"
          runbook: "/runbooks/harness-high-burn-rate"

      # Slow burn: 3× over 2h+1d
      - alert: HarnessSlowBurn
        expr: |
          (
            sum(rate(harness_requests_total{status!="success"}[2h]))
            / sum(rate(harness_requests_total[2h]))
          ) > 0.03
          and
          (
            sum(rate(harness_requests_total{status!="success"}[1d]))
            / sum(rate(harness_requests_total[1d]))
          ) > 0.03
        for: 15m
        labels: {severity: slack}
        annotations:
          summary: "Harness slow burn (3× over 2h+1d)"
```

Подробнее — в [Incident Runbook](/guide/incident-runbook).

## Что алертить, а что нет

**✓ Алертить:**

- Burn rate SLO (как выше).
- Полное исчерпание error budget (incident).
- Cost per session > SLO (1h окно).
- Eval pass rate < 80% (online, 24h окно).
- LLM provider outage (5xx rate >50% за 5m).
- Guardrails tripped > baseline ×3 (возможная атака).
- Agent-loop итераций p99 > 15 (возможный runaway).

**✗ Не алертить:**

- Отдельные 5xx — это noise, используйте SLO burn rate.
- Latency p50 — бесполезно для алертинга.
- CPU/memory (если не приводит к SLO-нарушению) — это infra-метрики, не product.
- High queue depth — SLO-latency уже ловит user-visible проблему.

Правило: **алерт должен требовать действия человека.** Если алерт приходит, и вы думаете «ну и ладно» — это не алерт, это noise.

## Oncall routing

- **Page (PagerDuty/OpsGenie):** SLO burn rate 14.4×, полная деградация, security incident (prompt injection detected).
- **Slack/Telegram:** Slow burn SLO, eval pass rate drop, cost per session trend.
- **Email/Daily digest:** Тренды за неделю, upcoming SLO refresh.

Для РФ-инсталляций под 152-ФЗ: алерты **не должны содержать ПДн** в payload (только метрики и хеши). Если нужно передать контекст — давайте ссылку на внутренний dashboard с авторизацией.

## Чек-лист

- [ ] Определены SLI: success rate, latency p99 (разделено по классам), cost per session, eval pass rate.
- [ ] SLO target'ы зафиксированы в документе, доступном всей команде.
- [ ] Error budget считается и отображается на dashboard'е.
- [ ] Multi-window multi-burn-rate alerts настроены.
- [ ] Каждый page-level alert имеет runbook.
- [ ] Oncall rotation определена (не «тот, кто первый увидел»).
- [ ] Алерты не содержат ПДн (152-ФЗ compliance).
- [ ] Раз в квартал проводится SLO review (target'ы корректируются).

## Что читать дальше

- [Observability](/guide/observability) — контекст, как SLO ложится на observability.
- [Incident Runbook](/guide/incident-runbook) — что делать, когда alert сработал.
- [Harness Metrics](/guide/harness-metrics) — источник данных для SLI.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/) — первоисточник по multi-burn-rate.
