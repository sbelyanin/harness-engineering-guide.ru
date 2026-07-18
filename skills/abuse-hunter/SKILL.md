---
name: abuse-hunter
description: Обнаружение и расследование batch-регистраций в SaaS. При доступе к базе пользователей (или экспортированному CSV/JSON) запускает многомерный анализ аномалий — кластеризация email-доменов, ритм регистраций, UA-фингерпринтинг, структура сессий, паттерны использования и потребление кредитов — и выдаёт scored abuse-отчёт с рекомендуемыми действиями. Используйте при расследовании подозрительных всплесков регистраций, credit fraud, abuse free-tier или account farming.
---

# Abuse Hunter — Skill для расследования batch-регистраций в SaaS

One-shot-расследование: есть ли на вашей SaaS-платформе batch-регистрации, farming аккаунтов, abuse бесплатных кредитов и другие злоупотребления.

## Когда использовать

- Обнаружили email-домен с аномально высоким объёмом регистраций
- Новые пользователи резко выросли, но conversion в платящих упал
- Скорость потребления бесплатных кредитов/credit резко ускорилась
- Подозреваете автоматизированную регистрацию

## Процесс расследования (6 шагов)

Выполняйте по порядку. На каждом шаге выводится промежуточный вывод; в конце формируется композитная оценка.

### Шаг 1: Кластеризация email-доменов

**Цель:** найти домены с аномальным объёмом регистраций

```sql
-- Статистика по email-доменам: ищем топ-подозрительные домены
SELECT
  SUBSTRING(email FROM '@(.+)$') AS domain,
  COUNT(*) AS user_count,
  MIN(created_at) AS first_signup,
  MAX(created_at) AS last_signup,
  EXTRACT(EPOCH FROM MAX(created_at) - MIN(created_at)) / 3600 AS span_hours
FROM users
GROUP BY domain
HAVING COUNT(*) > 10
ORDER BY user_count DESC
LIMIT 20;
```

**Критерии оценки:**
- 🔴 Один домен >100 регистраций + возраст домена <30 дней → высокий риск
- 🟡 Один домен 50–100 регистраций + регистрации сосредоточены в <72h → средний риск
- 🟢 Один домен <50 регистраций + равномерное распределение → низкий риск

**Проверка background домена:**
```bash
# WHOIS: дата создания и регистратор
whois <domain> | grep -iE "creation|registrar|name server"
# DNS: есть ли сайт и почтовая конфигурация
dig <domain> MX +short
dig <domain> A +short
# ICP filing (только для китайских доменов)
curl -s "https://api.vvhan.com/api/icp?url=<domain>" | jq .
```

### Шаг 2: Анализ временно́го паттерна регистраций

**Цель:** определить, является ли ритм регистраций органическим или batch-инъекцией

```sql
-- Регистрации по дням (подозрительный домен)
SELECT
  DATE(created_at) AS reg_date,
  COUNT(*) AS daily_count
FROM users
WHERE email LIKE '%@<suspect_domain>'
GROUP BY reg_date
ORDER BY reg_date;

-- Регистрации по часам (поиск пиков)
SELECT
  DATE(created_at) AS reg_date,
  EXTRACT(HOUR FROM created_at) AS reg_hour,
  COUNT(*) AS hourly_count
FROM users
WHERE email LIKE '%@<suspect_domain>'
GROUP BY reg_date, reg_hour
HAVING COUNT(*) > 10
ORDER BY hourly_count DESC;

-- Анализ интервалов между регистрациями (ключевой!)
WITH ordered AS (
  SELECT created_at,
    LAG(created_at) OVER (ORDER BY created_at) AS prev_at
  FROM users
  WHERE email LIKE '%@<suspect_domain>'
)
SELECT
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM created_at - prev_at)) AS median_interval_sec,
  PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM created_at - prev_at)) AS p90_interval_sec
FROM ordered
WHERE prev_at IS NOT NULL;
```

**Критерии оценки:**
- 🔴 Медианный интервал <60 секунд → автоматизированная регистрация
- 🟡 Медианный интервал 60–300 секунд + явные пики → подозрительный batch
- 🟢 Медианный интервал >300 секунд + отсутствие кластеризации → органическая регистрация

**Детекция переключения фаз:**
Разбейте регистрации по временным сегментам и проверьте наличие паттерна "сначала небольшой probing, потом массовый flood". Если он есть — это указывает на фазу тестирования → масштабирования.

### Шаг 3: Анализ паттернов email-префиксов

**Цель:** определить, созданы ли email-адреса вручную или сгенерированы программой

```sql
-- Распределение длин префиксов
SELECT
  LENGTH(SPLIT_PART(email, '@', 1)) AS prefix_len,
  COUNT(*) AS cnt
FROM users
WHERE email LIKE '%@<suspect_domain>'
GROUP BY prefix_len
ORDER BY cnt DESC;

-- Классификация паттернов префиксов
SELECT
  CASE
    WHEN SPLIT_PART(email, '@', 1) ~ '^[a-z]+$' THEN 'letters_only'
    WHEN SPLIT_PART(email, '@', 1) ~ '^[0-9]+$' THEN 'digits_only'
    WHEN SPLIT_PART(email, '@', 1) ~ '^[a-z0-9]{6}$' THEN '6char_alnum'
    WHEN SPLIT_PART(email, '@', 1) ~ '^[a-z0-9]{5}$' THEN '5char_alnum'
    ELSE 'other'
  END AS prefix_pattern,
  COUNT(*) AS cnt
FROM users
WHERE email LIKE '%@<suspect_domain>'
GROUP BY prefix_pattern
ORDER BY cnt DESC;
```

**Критерии оценки:**
- 🔴 >80% — фиксированная длина случайная строка (например, 6 alnum) → программная генерация
- 🟡 Смешанные паттерны, но высокая концентрация → полуавтомат
- 🟢 Длина и паттерны близки к нормальному распределению → органическая регистрация

### Шаг 4: UA-отпечатки и структура сессий

**Цель:** оценить диверсификацию регистрационного окружения

```sql
-- Богатство UA (подозрительный домен vs все пользователи)
-- Подозрительный домен
SELECT
  COUNT(DISTINCT session_id) AS total_sessions,
  COUNT(DISTINCT user_agent) AS unique_uas,
  ROUND(COUNT(DISTINCT user_agent)::NUMERIC / NULLIF(COUNT(DISTINCT session_id), 0), 4) AS ua_diversity
FROM sessions s
JOIN users u ON s.user_id = u.id
WHERE u.email LIKE '%@<suspect_domain>';

-- Все пользователи (baseline)
SELECT
  COUNT(DISTINCT session_id) AS total_sessions,
  COUNT(DISTINCT user_agent) AS unique_uas,
  ROUND(COUNT(DISTINCT user_agent)::NUMERIC / NULLIF(COUNT(DISTINCT session_id), 0), 4) AS ua_diversity
FROM sessions s
JOIN users u ON s.user_id = u.id
WHERE u.email NOT LIKE '%@<suspect_domain>';

-- Распределение количества сессий на пользователя
SELECT
  u.email LIKE '%@<suspect_domain>' AS is_suspect,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY session_count) AS median_sessions,
  PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY session_count) AS p90_sessions
FROM (
  SELECT user_id, COUNT(*) AS session_count
  FROM sessions GROUP BY user_id
) sc
JOIN users u ON sc.user_id = u.id
GROUP BY is_suspect;
```

**Критерии оценки:**
- 🔴 Разнообразие UA на порядок ниже, чем у всех пользователей → высокая конвергенция окружения
- 🟡 Разнообразие UA ниже, но не критично → требует дополнительных измерений
- 🟢 UA-распределение близко к общей популяции → норма

### Шаг 5: Поведение и время активации

**Цель:** определить, используются ли аккаунты сразу или "запасаются и активируются позже"

```sql
-- Интервал регистрация → первое использование
SELECT
  u.email LIKE '%@<suspect_domain>' AS is_suspect,
  COUNT(*) AS users_with_usage,
  PERCENTILE_CONT(0.5) WITHIN GROUP (
    ORDER BY EXTRACT(EPOCH FROM first_usage - u.created_at)
  ) AS median_activation_sec,
  PERCENTILE_CONT(0.9) WITHIN GROUP (
    ORDER BY EXTRACT(EPOCH FROM first_usage - u.created_at)
  ) AS p90_activation_sec
FROM users u
JOIN (
  SELECT user_id, MIN(created_at) AS first_usage
  FROM usage_events GROUP BY user_id
) ue ON u.id = ue.user_id
GROUP BY is_suspect;

-- Покрытие использованием
SELECT
  u.email LIKE '%@<suspect_domain>' AS is_suspect,
  COUNT(*) AS total_users,
  COUNT(ue.user_id) AS users_with_usage,
  ROUND(COUNT(ue.user_id)::NUMERIC / COUNT(*), 4) AS usage_rate
FROM users u
LEFT JOIN (
  SELECT DISTINCT user_id FROM usage_events
) ue ON u.id = ue.user_id
GROUP BY is_suspect;
```

**Критерии оценки:**
- 🔴 Медиана активации >1 час + usage rate <80% → паттерн "запас → активация"
- 🟡 Время активации выше нормы, но usage rate нормальный → требует дополнительных измерений
- 🟢 Время активации и usage rate близки к общей популяции → норма

### Шаг 6: Потребление кредитов / credit

**Цель:** количественно оценить реальный экономический ущерб

```sql
-- Сводка по потреблению кредитов подозрительным доменом
SELECT
  COUNT(*) AS accounts_with_credits,
  SUM(total_granted) AS total_credits_granted,
  SUM(total_consumed) AS total_credits_consumed,
  SUM(total_expired) AS total_credits_expired,
  ROUND(SUM(total_consumed)::NUMERIC / NULLIF(SUM(total_granted), 0), 4) AS consumption_rate
FROM credit_summary cs
JOIN users u ON cs.user_id = u.id
WHERE u.email LIKE '%@<suspect_domain>';

-- Топ-10 моделей по стоимости вызовов
SELECT
  model_name,
  COUNT(*) AS call_count,
  COUNT(DISTINCT user_id) AS unique_users,
  ROUND(SUM(cost_usd)::NUMERIC, 2) AS total_cost
FROM usage_events ue
JOIN users u ON ue.user_id = u.id
WHERE u.email LIKE '%@<suspect_domain>'
GROUP BY model_name
ORDER BY total_cost DESC
LIMIT 10;
```

## Композитная модель оценки

Каждое измерение оценивается 0–2 баллами, итого 12 баллов:

| Измерение | 0 (норма) | 1 (подозрительно) | 2 (высокий риск) |
|-----------|-----------|-------------------|------------------|
| Кластеризация доменов | <50 регистраций | 50–100 регистраций | >100 регистраций |
| Ритм регистраций | Интервал >5 мин | Интервал 1–5 мин | Интервал <1 мин |
| Паттерны префиксов | Естественное распределение | Частично упорядочено | >80% фиксированный паттерн |
| UA-фингерпринт | Нормальное разнообразие | Ниже нормы | На порядок ниже |
| Время активации | Норма | Медленнее | Явный паттерн "запас → использование" |
| Потребление кредитов | Низкое | Среднее | Массовый забор |

**Интерпретация общего балла:**
- 0–3 балла: ✅ Органическая пользовательская группа
- 4–7 баллов: ⚠️ Требуется наблюдение
- 8–12 баллов: 🚨 Высокая вероятность batch-злоупотребления, рекомендуется немедленная реакция

## Формат вывода

По завершении расследования выведите структурированный отчёт:

```
# Отчёт о расследовании abuse

## Целевой домен: xxx.yyy
## Время расследования: YYYY-MM-DD
## Общий балл: X / 12 (✅ / ⚠️ / 🚨)

### Оценки по измерениям
| Измерение | Балл | Ключевые находки |
|-----------|------|------------------|
| ... | ... | ... |

### Ключевой таймлайн
- Day 1: ...
- Day N: ...

### Оценка влияния
- Задействовано аккаунтов:
- Потреблено кредитов:
- Стоимость inference:

### Рекомендуемые действия
1. Немедленно: ...
2. Краткосрочно: ...
3. Долгосрочно: ...
```

## Шаблоны рекомендуемых действий

Рекомендации формируются автоматически на основе общего балла:

### 8–12 баллов (высокий риск)
1. **Немедленно:** заморозить все неиспользованные кредиты домена, приостановить новые регистрации
2. **Краткосрочно:** провести ручную проверку существующих аккаунтов домена, пометить кредиты к возврату
3. **Долгосрочно:** добавить в регистрационный флоу следующие защиты —
   - Проверка возраста email-домена (<30 дней требует дополнительной верификации)
   - Лимит частоты регистраций с одного домена (например, ≤5 в час)
   - Мониторинг диверсификации UA в реальном времени
   - Алертинг на аномальные интервалы между регистрациями

### 4–7 баллов (наблюдение)
1. Настроить дашборд мониторинга для домена
2. Установить пороговые алерты на объём регистраций
3. Пересматривать ситуацию еженедельно

### 0–3 балла (норма)
1. Архивировать отчёт, действий не требуется
2. Сохранить обычный мониторинг

## Адаптация

SQL выше написан на диалекте PostgreSQL. Если ваша база:
- **MySQL:** замените `SUBSTRING(... FROM ...)` на `SUBSTRING_INDEX()`, `PERCENTILE_CONT` эмулируйте подзапросами
- **MongoDB:** перепишите SQL на aggregation pipeline (`$group`, `$match`, `$project`)
- **CSV/JSON экспорт:** используйте Python pandas-скрипт, см. `scripts/analyze.py`

Если имена таблиц или полей отличаются, скажите вашу schema — я адаптирую запросы.
