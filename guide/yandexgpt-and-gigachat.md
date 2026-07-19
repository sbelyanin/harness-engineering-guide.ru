---
author: Harness Engineering Guide (RU)
title: "YandexGPT и GigaChat как провайдеры в Harness"
section: practice
description: "Как подключить YandexGPT (Yandex Cloud) и GigaChat / GigaChat MAX (Сбер) как model-провайдеров в harness: аутентификация, форматы tool-calling, IAM-токены, отличия от OpenAI-compatible API и чек-лист failover."
category: Practice
date: "2026-07-19"
---

# YandexGPT и GigaChat как провайдеры в Harness

> **Главный инсайт:** YandexGPT и GigaChat не дают «openai-compatible» API из коробки — у каждого своя аутентификация (IAM / OAuth-токен Сбер), свои форматы tool-calling и свои лимиты. Harness, рассчитанный на swap endpoint’а, на них споткнётся: нужна не «другая базовая URL», а отдельный adapter-слой с пересборкой сообщений, подписями для GigaChat и ротуемыми IAM-токенами для Yandex.

## Когда это нужно

- **152-ФЗ / локализация ПДн** — данные не должны уходить к зарубежным провайдерам
- **Гос. и окологос. контракты** — требования к реестру российского ПО
- **Cost-optimization** — на русскоязычных задачах YandexGPT/GigaChat часто дешевле западных frontier-моделей
- **Air-gapped контуры** — см. [On-Prem Harness](/guide/on-prem-harness); российские провайдеры дают dedicated-размещение

## Провайдеры на момент написания

| Провайдер | Семейство | Tool-calling | Контекст | API-стиль |
|-----------|-----------|--------------|----------|-----------|
| YandexGPT (Yandex Cloud) | yandexgpt, yandexgpt-lite | partial (Chat Completion) | 8K–32K | REST + IAM |
| GigaChat (Сбер) | base, plus, pro | partial (functions) | 8K–32K | REST + OAuth |
| GigaChat MAX | stealth-large | да (улучшенный) | до 128K | REST + OAuth |
| Tinkoff (T-Bank) | tt-large / tt-lite | partial | 8K–32K | REST |

Точные цифры и доступность меняются — сверяйтесь с официальной документацией провайдера перед выкаткой.

## Слой 1. Аутентификация

### YandexGPT — IAM-токены

YandexGPT работает через Yandex Cloud и требует **IAM-токен**, который живёт до 12 часов. Harness обязан его ротировать.

```python
import requests
from datetime import datetime, timedelta

class YandexIamProvider:
    def __init__(self, oauth_token: str, folder_id: str):
        self.oauth_token = oauth_token
        self.folder_id = folder_id
        self._cached_iam = None
        self._expires_at = datetime.min

    def get_iam_token(self) -> str:
        # За 10 минут до истечения обновляем
        if self._cached_iam and datetime.utcnow() < self._expires_at - timedelta(minutes=10):
            return self._cached_iam
        resp = requests.post(
            "https://iam.api.cloud.yandex.net/iam/v1/tokens",
            json={"yandexPassportOauthToken": self.oauth_token},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._cached_iam = data["iamToken"]
        self._expires_at = datetime.fromisoformat(data["expiresAt"].replace("Z", "+00:00"))
        return self._cached_iam
```

- `folder_id` обязателен в теле запроса к `llm.cloud.yandex.net`/`completionAsync`
- Для production — храните OAuth-токен в vault, не в env
- Запросы к YandexGPT **асинхронные**: `completionAsync` → поллинг `operation` → результат. Синхронный режим есть, но с задержками

### GigaChat — OAuth client_credentials

GigaChat использует OAuth2 `client_credentials` с коротким access-токеном (~30 минут). Запросы надо **подписывать** (взаимная TLS-аутентификация для production).

```python
import base64
import requests

class GigaChatAuth:
    AUTH_URL = "https://ngw.devices.sberbank.ru/ru/v1/oauth"

    def __init__(self, client_id: str, client_secret: str, scope: str = "GIGACHAT_API_PERS"):
        self.credentials = base64.b64encode(
            f"{client_id}:{client_secret}".encode()
        ).decode()
        self.scope = scope
        self._access = None
        self._expires_at = 0

    def get_access_token(self) -> str:
        import time
        if self._access and time.time() < self._expires_at - 60:
            return self._access
        resp = requests.post(
            self.AUTH_URL,
            headers={
                "Authorization": f"Basic {self.credentials}",
                "RqUID": str(__import__("uuid").uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=f"scope={self.scope}",
            timeout=10,
            # verify="ru_cer/root.crt"  # для production — сертификат Минцифры
        )
        resp.raise_for_status()
        data = resp.json()
        self._access = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 1800)
        return self._access
```

**Важно для harness:**
- Для production запрашивайте corporate-scope (`GIGACHAT_API_CORP`), не персональный
- mTLS с сертификатом Минцифры требуется для определённых scopes — без него запросы отлетают с 403
- Заголовок `RqUID` (UUID запроса) **обязателен** — без него 400

## Слой 2. Adapter над сообщениями

Ни YandexGPT, ни GigaChat не принимают «голый» OpenAI-формат. Нужен adapter, который:

1. Нормализует `role` — оба провайдера используют `system`/`user`/`assistant`/`function`, но Yandex требует `system` отдельным полем
2. Преобразует tool-calls — у GigaChat функции описываются иначе (поле `functions`, не `tools`)
3. Режет контекст — у младших моделей жёсткое окно 8K

```python
def openai_to_gigachat(messages: list[dict], tools: list[dict] | None) -> dict:
    payload: dict = {"messages": []}
    system_parts = []
    for m in messages:
        if m["role"] == "system":
            system_parts.append(m["content"])
        else:
            payload["messages"].append({"role": m["role"], "content": m["content"]})
    if system_parts:
        # GigaChat требует system первым сообщением
        payload["messages"].insert(0, {"role": "system", "content": "\n".join(system_parts)})
    if tools:
        payload["functions"] = [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "parameters": t["function"].get("parameters", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]
        payload["function_call"] = "auto"
    return payload


def gigachat_to_openai(resp: dict) -> dict:
    choice = resp["choices"][0]
    msg = choice["message"]
    # GigaChat возвращает function_call вместо tool_calls
    if "function_call" in msg:
        msg["tool_calls"] = [{
            "id": "call_giga",
            "type": "function",
            "function": {
                "name": msg["function_call"]["name"],
                "arguments": msg["function_call"]["arguments"],
            },
        }]
    return {"choices": [{"message": msg, "finish_reason": choice.get("finish_reason", "stop")}]}
```

## Слой 3. Tool-calling — что починить в harness

Русскоязычные модели **хуже** frontier держат сложные tool-схемы. Эмпирические правила:

1. **Максимум 5–7 tools за раз.** Больше — модели начинают галлюцинировать имена
2. **Русские описания предпочтительнее.** Tool descriptions на английском работают, но recall падает на 15–25%
3. **JSON-схема без `$ref` и `oneOf`.** Младшие модели не умеют; упрощайте до `enum` + явных полей
4. **Мandatory arguments explicit.** Не надейтесь на дефолты — прописывайте их в prompt

Если tool-calling нестабилен — переходите в **text-mode** с явным JSON-блоком:

```
Вызови tool, верни результат строго в виде:
```json
{"tool": "search_docs", "args": {"query": "..."}}
```
```

Harness парсит fenced JSON, маппит на tool-call. См. [Tool System](/guide/tool-system).

## Слой 4. Token economy под кириллицу

На YandexGPT/GigaChat кириллица считается **дешевле**, чем на зарубежных моделях (токенизатор натренирован на русском). Но оценка стоимости — в рублях/токен, и формулы отличаются от OpenAI.

- Сверяйтесь со счётчиком в личном кабинете **до** запуска больших eval-батчей
- Используйте `stream=true` для длинных ответов — иначе таймауты на 30+ секундах
- Кешируйте `completion` для идемпотентных системных промптов

См. [Cyrillic Tokenization](/guide/cyrillic-tokenization) — детальный разбор токен-экономики.

## Слой 5. Rate limits и failover

| Поведение | Причина | Реакция harness |
|-----------|---------|-----------------|
| 429 Too Many Requests | RPM/TPM лимит | exponential backoff 1s → 30s |
| 401 Unauthorized | Истёк IAM/OAuth | обновить токен, ретрай |
| 403 Forbidden | Сертификат / scope | fail, алерт — не ретрай |
| 502/503 | Балансировщик провайдера | ретрай на другой endpoint |
| Долгий поллинг (>60s) | cold start модели | таймаут + fallback на lite |

**Failover-стратегия для RU-context:**

```python
PROVIDER_CHAIN = [
    {"name": "yandexgpt", "model": "yandexgpt", "timeout_ms": 20000},
    {"name": "gigachat", "model": "GigaChat-2-Max", "timeout_ms": 30000},
    # Western fallback только если compliance позволяет:
    # {"name": "claude", "model": "claude-sonnet", "timeout_ms": 15000},
]

async def call_with_failover(messages, tools):
    last_err = None
    for prov in PROVIDER_CHAIN:
        try:
            return await providers[prov["name"]].complete(
                messages, tools, timeout_ms=prov["timeout_ms"]
            )
        except (RateLimitError, ProviderUnavailable) as e:
            last_err = e
            continue
    raise last_err
```

## Антипаттерны

- **Хардкодить IAM-токен в env** — протухнет через 12 часов, агент упадёт посреди task’а
- **Использовать персональный scope GigaChat (`_PERS`) в production** — violation compliance, токен привязан к физлицу
- **Полагаться на «OpenAI-compatible» обёртки** без тестов tool-calling — они часто теряют `function_call`-структуру
- **Гнать весь трафик через один провайдер** — российские облачные регионы иногда лежат по 2–4 часа; нужен второй

## Что почитать

- [Russian LLM в Harness](/guide/russian-llm-harness) — общая специфика русскоязычных моделей
- [Tool System](/guide/tool-system) — проектирование tool-описаний
- [Cyrillic Tokenization](/guide/cyrillic-tokenization) — токен-экономика под RU
- [On-Prem Harness](/guide/on-prem-harness) — air-gapped развёртывания российских моделей
- [compliance-152fz](/guide/compliance-152fz) — юридический контекст хранения ПДн
