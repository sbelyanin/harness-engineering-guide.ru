---
author: Harness Engineering Guide (RU)
title: "Compliance: Harness и 152-ФЗ"
section: practice
description: "Как строить harness, обрабатывающий персональные данные, в рамках 152-ФЗ: классификация ПДн, согласие и цели, хранение и удаление, журнал доступа, безопасность tool-calls и чек-лист перед запуском."
category: Practice
date: "2026-07-19"
---

# Compliance: Harness и 152-ФЗ

> **Главный инсайт:** 152-ФЗ требует не «хранить в РФ», а **обрабатывать по целям**. AI-агент, который читает тикетты с ПДн, шлёт их в LLM-провайдера, логирует и кеширует — это full-cycle оператор ПДн. Не спроектировав harness под legal-требования, вы получаете violation на каждом ходу: незаконная передача third-party, сверхцелевая обработка, отсутствие права на удаление.

## Когда это применимо

152-ФЗ включается, когда harness обрабатывает **персональные данные (ПДн)** — любую информацию, относящуюся к определённому физлицу. В AI-агентах это почти всегда:

- Email, телефон, ФИО пользователя в тикеттах / чатах / CRM
- Cookie / IP / device-id, привязанные к лицу
- Содержание переписки (косвенные ПДн — упоминания третьих лиц, адреса, номера карт)
- Логи поведения (что искал, что купил, куда кликнул)

Даже **анонимизированные** данные часто юридически остаются ПДн, если их можно обратно связать с лицом (pseudonymization ≠ anonymization).

## Слой 1. Классификация ПДн

Определите категорию обрабатываемых ПДн — от неё зависит уровень защищённости:

| Категория | Примеры | Требования |
|-----------|---------|------------|
| Общедоступные | ФИО в корп. справочнике | минимальные |
| Иные (обычные) | email, телефон клиента | УЗ-1, УЗ-2 |
| Специальные | здоровье, национальность, религия | УЗ-3, УЗ-4 |
| Биометрические | фото-верификация, голос | УЗ-4, отдельная лицензия |

Для типового agent-use-case (support-бот, внутренний ассистент) — **обычные ПДн, УЗ-1 или УЗ-2**. Это означает: шифрование при передаче, разграничение доступа, журнал операций.

```python
from enum import IntEnum

class PDnCategory(IntEnum):
    PUBLIC = 0
    ORDINARY = 1
    SPECIAL = 2
    BIOMETRIC = 3

class PDnClassification:
    """Классификатор полей — должен быть настроен под вашу schema."""
    RULES = {
        "email": PDnCategory.ORDINARY,
        "phone": PDnCategory.ORDINARY,
        "full_name": PDnCategory.ORDINARY,
        "inn": PDnCategory.ORDINARY,
        "passport_series": PDnCategory.ORDINARY,
        "health_notes": PDnCategory.SPECIAL,
        "voice_recording": PDnCategory.BIOMETRIC,
    }

    @classmethod
    def classify(cls, field_name: str) -> PDnCategory:
        return cls.RULES.get(field_name.lower(), PDnCategory.PUBLIC)
```

## Слой 2. Цели обработки и согласие

152-ФЗ требует **целевой** обработки: ПДн используются только для заявленных целей. AI-агент, который «видит» ПДн в контексте, должен иметь explicit цель.

### Согласие пользователя

- **Явное согласие** на обработку ПДн — checkbox при онбординге, не pre-ticked
- **Цель** — конкретная: «обработка обращений в support», «формирование рекомендаций»
- **Список действий** — сбор, запись, передача LLM-провайдеру, удаление

Храните согласие в БД оператора ПДн, не в логах агента.

### Сверхцелевая обработка — главная ловушка

Если harness собрал email для «обработки тикетты», а потом тот же лог скармливается в eval-пайплайн для «улучшения модели» — это **сверхцелевая обработка**, нарушение ст. 5 п. 2. Каждый пайплайн должен иметь свою цель и своё согласие.

```python
class PurposeGate:
    """Проверка, что операция соответствует цели сбора ПДн."""
    ALLOWED_PURPOSES = {
        "support_ticket": ["read_ticket", "draft_response", "send_reply"],
        "analytics": ["aggregate_stats"],  # без сырых ПДн
        "model_training": ["pseudonymize", "fine_tune"],  # только псевдонимизированные
    }

    @classmethod
    def check(cls, collection_purpose: str, action: str) -> bool:
        return action in cls.ALLOWED_PURPOSES.get(collection_purpose, [])
```

## Слой 3. Передача third-party (LLM-провайдеру)

Передача ПДн в LLM-API — это **передача третьей стороне**. Зависит от провайдера:

| Провайдер | Статус | Требование |
|-----------|--------|------------|
| YandexGPT (Yandex Cloud, РФ) | обработчик в РФ | доп. соглашение с Yandex |
| GigaChat (Сбер, РФ) | обработчик в РФ | доп. соглашение со Сбером |
| Claude / OpenAI / Gemini (зарубеж) | трансграничная передача | отдельное согласие пользователя, уведомление Роскомнадзора |

**Для зарубежных провайдеров** одного согласия в TOS недостаточно. Нужен либо:
- Явный checkbox «согласен на трансграничную передачу»
- Pseudonymization перед передачей (см. ниже)
- Локальная модель (см. [Open-Source LLM-стек](/guide/open-source-llm-stack))

### Pseudonymization перед LLM-call

```python
import re
import hashlib
from typing import Callable

class PDnPseudonymizer:
    PATTERNS: list[tuple[str, Callable[[re.Match], str]]] = [
        # Email → хеш
        (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
         lambda m: f"EMAIL_{hashlib.sha256(m.group().encode()).hexdigest()[:8]}"),
        # Российский телефон
        (re.compile(r"\+7[\d\-\(\)\s]{10,}\d"),
         lambda m: f"PHONE_{hashlib.sha256(m.group().encode()).hexdigest()[:8]}"),
        # Паспорт серия+номер
        (re.compile(r"\b\d{4}\s?\d{6}\b"),
         lambda m: f"PASSPORT_{hashlib.sha256(m.group().encode()).hexdigest()[:8]}"),
        # ИНН
        (re.compile(r"\b\d{10}|\d{12}\b"),
         lambda m: f"INN_{hashlib.sha256(m.group().encode()).hexdigest()[:8]}"),
    ]

    @classmethod
    def mask(cls, text: str) -> str:
        for pattern, repl in cls.PATTERNS:
            text = pattern.sub(repl, text)
        return text
```

Храните mapping `EMAIL_abc12345 → user@example.com` в отдельной защищённой таблице. LLM видит только токен, не саму ПДн.

## Слой 4. Хранение и удаление

### Сроки хранения

- **Не храните дольше, чем заявлено в согласии.** Если согласие — «до закрытия тикетты + 30 дней», агент не должен кешировать содержимое в долгосрочной memory навсегда
- **Memory-уровни (см. [Memory & Context](/guide/memory-and-context)) под TTL**:
  - Session memory — часы/дни
  - Long-term summaries — недели/месяцы с TTL
  - Eval-датасеты — отдельный режим (pseudonymized или aggregated)

### Право на удаление (ст. 17 п. 5)

Пользователь может потребовать удалить ПДн. Harness обязан уметь:

1. Найти все записи с ПДн пользователя по идентификатору
2. Удалить из: основной БД, memory-логов, context-кеши, eval-датасетов
3. Перезаписать summaries, где пользователь упомянут
4. Подтвердить удаление журналом

```python
async def forget_user(user_id: str) -> ForgetReport:
    """Реализация права на удаление."""
    report = ForgetReport(user_id=user_id)

    # 1. Основная БД — каскадное удаление
    report += await db.delete_user_records(user_id)

    # 2. Session-логи агента
    report += await session_store.purge(user_id)

    # 3. Long-term memory (включая summaries)
    report += await memory_store.purge_user_mentions(user_id)

    # 4. Eval-датасеты — проверить, были ли данные использованы
    report += await eval_store.audit_user_data(user_id)

    # 5. Журнал операций сохраняется, но без самих ПДн
    await audit_logger.write({
        "action": "user_forgotten",
        "user_hash": hash_user_id(user_id),
        "ts": datetime.utcnow().isoformat(),
        "details": report.to_dict(),
    })
    return report
```

**Memory — самая коварная поверхность.** LLM-generated summaries часто перефразируют ПДн так, что поиск по user_id их не находит. Нужен полный re-scan всех summaries через pseudonymized-LLM-классификатор.

## Слой 5. Журнал доступа (ст. 19 п. 4)

УЗ-2 и выше требуют журнал регистрации всех операций с ПДн:

- **Кто** обратился (session_id, user_id оператора)
- **Когда** (timestamp с секундами)
- **Что** сделал с ПДн (read / write / transfer / delete)
- **Какие записи** затронуты
- **Цель** операции

```python
def log_pdn_operation(
    operator: str,
    action: str,
    records: list[str],
    purpose: str,
    pdn_category: PDnCategory,
):
    audit_logger.write({
        "ts": datetime.utcnow().isoformat(),
        "operator": operator,
        "action": action,            # read | write | transfer | delete
        "records_hashes": [hash_record(r) for r in records],  # не сами ПДн!
        "purpose": purpose,
        "category": pdn_category.name,
        "retention_days": 365 * 3,    # журнал хранится 3 года
    })
```

Журнал сам по себе не должен содержать ПДн — только хеши идентификаторов.

## Слой 6. Безопасность tool-calls

Tools — самая частая точка утечки ПДн:

- `send_email(to=user_email, body=...)` — ПДн в args
- `search_crm(query="Иван Иванов, паспорт ...")` — ПДн в поисковом запросе
- `http_post(url=external_api, body=user_data)` — передача третьей стороне

```python
# Tool wrapper, который проверяет операции с ПДн
def pdn_aware_tool(tool: Tool) -> Tool:
    @wraps(tool.func)
    async def wrapper(**kwargs):
        # Классификация аргументов
        for k, v in kwargs.items():
            cat = PDnClassification.classify(k)
            if cat >= PDnCategory.ORDINARY:
                log_pdn_operation(
                    operator=session.user_id,
                    action="read",
                    records=[v],
                    purpose=session.purpose,
                    pdn_category=cat,
                )

        # Проверка, что destination — разрешённый
        if tool.name.startswith("http_") and not is_allowed_endpoint(kwargs.get("url")):
            raise ComplianceError(f"External transfer to {kwargs.get('url')} blocked")

        return await tool.func(**kwargs)
    return replace(tool, func=wrapper)
```

## Слой 7. Локализация хранения

С 1 сентября 2022 г. — «закон о локализации»: ПДн граждан РФ при первичном сборе должны записываться в базу на территории РФ. Это не запрет на трансграничную передачу, но **первичная запись** — российская.

Для harness это означает:
- Основная БД оператора — в РФ (Yandex Cloud, Selectel, Cloud.ru)
- Cloudflare Workers / Vercel Edge можно для фронта, но не для primary DB writes
- Logs в реальном времени — лучше в РФ-логирование, не в зарубежный Datadog/Sentry

## Чек-лист перед production-запуском

- [ ] Определены категории ПДн, попадающих в harness
- [ ] Получено согласие пользователей под explicit-цели
- [ ] Цели обработки описаны в политике ПДн
- [ ] Каждый пайплайн (включая eval) проверен на сверхцелевую обработку
- [ ] Трансграничная передача (если есть) оформлена согласием
- [ ] Внедрена pseudonymization перед LLM-call’ами к зарубежным провайдерам
- [ ] Memory-уровни под TTL, право на удаление задокументировано
- [ ] Журнал доступа пишет хеши, не сами ПДн
- [ ] Tool-wrapper’ы логируют операции с ПДн
- [ ] Primary DB — в РФ
- [ ] Проведена оценка вреда (ст. 19 п. 4) — для УЗ-2 и выше
- [ ] Назначен ответственный за ПДн в команде

## Что почитать

- [Guardrails](/guide/guardrails) — trust-границы и модели разрешений
- [Memory & Context](/guide/memory-and-context) — TTL и cleanup для memory
- [On-Prem Harness](/guide/on-prem-harness) — air-gapped для УЗ-3+
- [YandexGPT и GigaChat](/guide/yandexgpt-and-gigachat) — РФ-провайдеры, упрощающие compliance
- [Open-Source LLM-стек](/guide/open-source-llm-stack) — self-hosted как путь к локализации

## Источники

- [Федеральный закон № 152-ФЗ «О персональных данных»](http://pravo.gov.ru/proxy/ips/?docbody=&nd=102141659)
- [Постановление Правительства РФ № 1119](http://government.ru/docs/all/68182/) — уровни защищенности ПДн
- [Приказ ФСТЭК России № 21](https://fstec.ru/dokumenty/vse-dokumenty/spetsialnye-normativnye-dokumenty/detail-page?pubid=5443) — требования к средствам защиты

*Статья носит инженерный характер и не является юридической консультацией. Для production-внедрения согласуйте с DPO.*
