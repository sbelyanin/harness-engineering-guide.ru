---
author: Harness Engineering Guide (RU)
title: "Incident Runbook: типовые инциденты Harness"
section: practice
description: "Что делать, когда harness упал в production: model outage, tool deprecation, prompt injection detected, cost spike, context-window exhaustion. Runbook'и для каждого класса инцидентов + postmortem template с акцентом на LLM-специфику."
category: Practice
date: "2026-07-23"
---

# Incident Runbook: типовые инциденты Harness

> **Главный инсайт:** Большинство incident'ов в harness — не «сервис лежит», а «сервис отвечает, но плохо». Это требует другого мышления: диагноз — не «какой под упал», а «какая часть pipeline'а сломалась: model, tool, guardrail, budget». Этот гайд — карта типовых сценариев и шагов.

## Шкала инцидентов

| Уровень | Что значит | Reaction time | Кто участвует |
|---------|-----------|---------------|---------------|
| **SEV-1** | Production сломан для всех пользователей | <5 min to acknowledge | Oncall + team lead + comms |
| **SEV-2** | Production сломан для подмножества или деградировал | <15 min | Oncall |
| **SEV-3** | Заметная деградация, users still can use | <1h during business hours | Oncall, может ждать утренней очереди |
| **SEV-4** | Cosmetic / edge case | Next business day | Triage в backlog |

**Главный принцип:** не тот SEV, «как сильно страшно», а тот, **как быстро надо реагировать**.

## Типовые инциденты

### 1. Model provider outage (SEV-1/SEV-2)

**Симптомы:**

- `harness_errors_total{class="model_api"}` растёт.
- `harness_llm_latency_seconds` скачет (rate limiting от provider'а).
- Burn rate SLO пробил 14.4× порог.

**Diagnosis (5 минут):**

1. Проверить provider status page (Yandex Cloud / Sber API / Anthropic status).
2. Посмотреть на метрику `harness_llm_latency_seconds{provider=X}` — если растёт только один provider, это он.
3. Глянуть trace_id из alert'а — что возвращает API? 5xx, 429, timeout?

**Remediation:**

- **Если есть multi-provider failover** (см. [Russian LLM в Harness](/guide/russian-llm-harness#harness-toml)) — harness должен переключиться автоматически. Если не переключился — failover сломан, нужно ручное переключение.
- **Если failover'а нет** — включить feature flag `model_provider: fallback` (заранее настроенный на более дорогой/медленный, но живой).
- **Если живых provider'ов нет** — graceful degradation: harness возвращает «сервис временно недоступен, попробуйте через N минут», не падая с 5xx.

**Post-incident:**

- Если failover не сработал — почему? (метрика? config? bug?)
- Обновить status dashboard с публичной информацией (твит/status page).
- Документировать RCA (root cause analysis).

### 2. Tool deprecation / breakage (SEV-2/SEV-3)

**Симптомы:**

- `harness_tool_calls_total{name=X,status="error"}` растёт.
- В traces видно, что agent-loop делает много итераций и не может завершить (tool каждый раз возвращает ошибку).

**Diagnosis:**

1. Посмотреть последние изменения в tool `X` — был ли деплой?
2. Проверить API upstream'а, который tool вызывает.
3. Глянуть traces — какой именно error message возвращает tool?

**Remediation:**

- **Если tool сломался без нашего участия** (например, upstream API изменился) — hotfix: отключить tool в registry, либо добавить fallback на старый endpoint.
- **Если tool обновили мы** — rollback версии tool'а.
- **Если tool не критичен** — disable в registry, harness должен работать без него (с ухудшенным UX).

**Prevention:**

- Tool calls должны иметь **strict schema validation** — если upstream возвращает не то, что ожидается, это ловится на test-этапе, а не в production.
- Smoke-тесты каждого tool'а перед deploy (см. [Eval Infrastructure](/guide/eval-infrastructure)).

### 3. Prompt injection detected (SEV-1 / Security)

**Симптомы:**

- `harness_guardrails_tripped_total{rule="prompt_injection"}` растёт (в 3+ раза от baseline).
- Конкретный user_id_hashed появляется в алертах несколько раз за час.

**Diagnosis:**

1. **Не паниковать, но быстро.** Если guardrail сработал — это **good news**: harness защитился. Задача — понять, есть ли user'ы, у которых guardrail НЕ сработал.
2. Посмотреть логи за последние 24h на похожие patterns (по signature атаки).
3. Проверить метрику `harness_tool_calls_total{name="execute_sql",status="blocked"}` — были ли попытки выполнить опасные действия?

**Remediation:**

- **Если атака одномоментная (1 user):** заблокировать user_id в auth-слое, не в harness.
- **Если атака распределённая:** включить strict-mode guardrails (более жёсткие regex/classifier thresholds).
- **Если guardrail пропустил часть атак:** проанализировать паттерны, обновить rules, прогнать через eval corpus заново.
- **Если был data leakage (model раскрыла system prompt):** считать, что вся система скомпрометирована — обновить secrets, пересобрать prompts.

**Post-incident (security):**

- Подробный RCA с timeline.
- Обновить guardrail rules на основе новых паттернов.
- Документировать attack signature в skills/abuse-hunter (см. [skills](/skills)).

### 4. Cost spike (SEV-2)

**Симптомы:**

- `harness_request_cost_usd_total` растёт быстрее, чем в среднем за неделю.
- `harness_tokens_consumed_total{kind="prompt"}` растёт disproportionately к `output` (context grows).
- `harness_agent_iterations_per_session` p99 вырос (много итераций → много token'ов).

**Diagnosis:**

1. Посмотреть, **какие** session'ы тратят больше — dashboard per-session cost.
2. Если конкретный user/session — это anomaly, не trend.
3. Если общее увеличение — что изменилось? Новый prompt template? Новый tool с длинным output? Модель обновилась (другой reasoning)?

**Remediation:**

- **Hard cap:** временно опустить per-session token budget (например, с 100K до 50K).
- **Если дело в модели** — переключиться на более дешёвую для некритичных session'ов (GigaChat vs YandexGPT Pro, см. [YandexGPT и GigaChat](/guide/yandexgpt-and-gigachat)).
- **Если дело в prompt template** — откатить шаблон.

**Prevention:**

- Cost budget alarms на daily/hourly уровне (см. [Alerting и SLO](/guide/alerting-and-slo)).
- Hard cap на per-session cost в harness config.

### 5. Context-window exhaustion (SEV-3)

**Симптомы:**

- `harness_errors_total{class="context_length"}` растёт.
- В traces видно, что session упала после N итераций из-за ошибки модели.

**Diagnosis:**

1. Какие session'ы упали — типичный pattern (long task / verbose tool output).
2. Сколько token'ов накопилось в context к моменту ошибки.

**Remediation:**

- **Увеличить model context window** (если поддерживается): переключиться на YandexGPT 4 Pro (32K) или GigaChat MAX (128K).
- **Memory compaction:** добавить шаг «summarize history» в agent-loop (см. [Memory & Context](/guide/memory-and-context)).
- **Tool output truncation:** ограничить размер ответа от verbose tool'ов.

### 6. Eval regression (SEV-3)

**Симптомы:**

- `eval_pass_rate` offline dropped на 5+ пунктов после deploy.
- Online evals показывают рост низких scores за последние 24h.

**Diagnosis:**

1. Сравнить before/after по конкретным eval cases — какие ухудшились?
2. Связать с деплоем: что поменялось в model / prompt / tool'ах?

**Remediation:**

- **Rollback deploy**, если регрессия существенна.
- Если rollback невозможен — mitigation: дополнительный prompt engineering, более жёсткий guardrail на проблемные паттерны.

## Postmortem template

Каждый SEV-1/SEV-2 инцидент требует postmortem'а в течение 48 часов. Template:

```markdown
# Postmortem: <incid_title>

**Date:** YYYY-MM-DD  
**Severity:** SEV-X  
**Incident duration:** Xh Ym  
**Lead:** <name>  
**Status:** Final / Draft

## Summary

<1-2 параграфа: что произошло, какой impact на пользователей, сколько
длилось. Без технических деталей — для менеджера/stakeholder'а.>

## Impact

- Пользователей затронуто: ~N
- Запросов упало: ~M
- Cost impact: $X (если применимо)
- SLI нарушен: <success rate / latency / ...>

## Timeline (UTC)

- **HH:MM** — Metric alert triggered: <link to alert>
- **HH:MM** — Oncall acknowledged.
- **HH:MM** — Mitigation applied: <action>.
- **HH:MM** — Recovery confirmed: metrics returned to baseline.

## Root Cause

<Что именно сломалось и почему. Не «human error», а почему система
допустила ошибку.>

## What Went Well

- <Автоматизация сработала> 
- <Traces дали быстрый diagnosis>

## What Went Poorly

- <Alert был слишком поздним>
- <Runbook отсутствовал>
- <Communication был медленным>

## Action Items

- [ ] (Owner: ...) Fix <root cause> by YYYY-MM-DD
- [ ] (Owner: ...) Add runbook for <scenario>
- [ ] (Owner: ...) Add metric/alert for <early detection>

## Lessons Learned

<Что изменим в процессах, чтобы такого не повторилось.>
```

Шаблон в виде skill'а — `skills/incident-postmortem/` (в разработке).

## Чек-лист готовности к инцидентам

- [ ] Для каждого page-level alert есть runbook (с конкретными шагами).
- [ ] Oncall rotation определена и documented.
- [ ] Communication channels настроены заранее (Slack channel, status page).
- [ ] Rollback процедура для каждого deploy documented (и протестирована).
- [ ] Graceful degradation mode для каждого критичного dependency.
- [ ] Postmortem template готов и доступен.
- [ ] Blameless culture — postmortem ищет системные причины, а не виноватых.

## Что читать дальше

- [Observability](/guide/observability) — источники данных для diagnosis.
- [Alerting и SLO](/guide/alerting-and-slo) — какие алерты запускают реакцию.
- [Error Handling](/guide/error-handling) — классификация ошибок.
- [Guardrails](/guide/guardrails) — защита от prompt injection.
- [Google SRE Workbook — Postmortems](https://sre.google/workbook/postmortems/) — канон по blameless postmortem'ам.
