---
title: "Guardrails"
section: core-concepts
author: Nexu
---

# Guardrails

> **Главный инсайт:** Агент без guardrails — это ответственность. Модель сделает ровно то, что ей сказали, — в том числе то, что велит prompt injection. Guardrails — это слой разрешений между «модель хочет сделать X» и «harness реально делает X».

## Зачем нужны Guardrails

Модель генерирует текст. Этот текст включает tool-вызовы. harness выполняет эти tool-вызовы. Значит, всё, что влияет на вывод модели, влияет на действия harness — включая вредоносный контент в файлах, веб-страницах или сообщениях пользователя.

Это и есть **prompt injection**: злоумышленник встраивает инструкции в данные, которые агент читает, и модель следует этим инструкциям вместо исходной задачи. Без guardrails prompt injection может:

- Удалить файлы (`rm -rf /`)
- Экзфильстрировать переменные окружения (API-ключи, токены)
- Выполнить произвольный код на хосте
- Отправлять несанкционированные сообщения от имени пользователя

Guardrails делают harness окончательным авторитетом в том, какие действия разрешены, независимо от того, что просит модель.

## Модель trust-границы

У любого harness есть trust-граница между моделью и операционной средой. harness опосредует все переходы:

```
┌──────────────────────────────────┐
│           MODEL SPACE            │
│  (рассуждения, запросы tool)     │
└────────────┬─────────────────────┘
             │ запрос tool-вызова
             ▼
┌──────────────────────────────────┐
│         GUARDRAIL LAYER          │
│  Проверка разрешения → Allow/Deny│
└────────────┬─────────────────────┘
             │ одобренный вызов
             ▼
┌──────────────────────────────────┐
│        EXECUTION SPACE           │
│  (файловая система, сеть, shell) │
└──────────────────────────────────┘
```

Слой guardrail перехватывает каждый tool-вызов перед выполнением. Он может:
- **Allow** — выполнить как запрошено
- **Deny** — вернуть модели ошибку
- **Modify** — переписать вызов (например, ограничить путь файла безопасной директорией)
- **Prompt** — спросить одобрение у человека перед продолжением

## Модели разрешений

### Allow-list (строгая)

Разрешены только явно указанные действия. Всё остальное запрещено по умолчанию:

```python
ALLOWED_TOOLS = {
    "read_file": {"paths": ["/workspace/**"]},
    "write_file": {"paths": ["/workspace/**"]},
    "run_command": {"commands": ["npm test", "npm run build"]},
}

def check_permission(tool_name: str, args: dict) -> bool:
    if tool_name not in ALLOWED_TOOLS:
        return False
    policy = ALLOWED_TOOLS[tool_name]
    if "paths" in policy:
        return any(fnmatch(args.get("path", ""), p) for p in policy["paths"])
    if "commands" in policy:
        return args.get("command") in policy["commands"]
    return True
```

### Deny-list (разрешительная)

Разрешено всё, кроме явно заблокированных действий:

```python
BLOCKED_PATTERNS = [
    (r"rm\s+-rf\s+/", "Refusing to delete root filesystem"),
    (r"curl.*\|\s*sh", "Refusing to pipe remote script to shell"),
    (r"env\s+|printenv|echo\s+\$", "Refusing to expose environment variables"),
]

def check_command(command: str) -> tuple[bool, str]:
    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, command):
            return False, reason
    return True, ""
```

### Многоуровневое одобрение

Разные уровни риска запускают разные flow одобрения:

| Уровень риска | Примеры | Действие |
|-----------|----------|--------|
| **Low** | Чтение файлов, поиск | Автоодобрение |
| **Medium** | Запись файлов, запуск тестов | Автоодобрение с логированием |
| **High** | Выполнение shell-команд, сетевые запросы | Требует одобрения человеком |
| **Critical** | Удаление файлов, git push, отправка сообщений | Всегда требует явного одобрения |

```python
def get_risk_level(tool_name: str, args: dict) -> str:
    if tool_name == "read_file":
        return "low"
    if tool_name == "write_file":
        return "medium"
    if tool_name == "run_command":
        cmd = args.get("command", "")
        if any(k in cmd for k in ["rm", "git push", "curl"]):
            return "critical"
        return "high"
    return "medium"
```

## Sandboxing

Guardrails обеспечивают политику; sandbox — изоляцию. Sandbox — это ограниченная среда выполнения, лимитирующая, что код может сделать на уровне ОС:

| Технология | Уровень изоляции | Оверхед | Сценарий |
|-----------|----------------|----------|----------|
| **chroot** | Только файловая система | Минимальный | Базовое ограничение путей |
| **Docker** | Процесс + файловая система + сеть | Низкий | Разработка, CI/CD |
| **Firecracker microVM** | Полная VM | Средний | Production multi-tenant |
| **gVisor** | Уровень syscall | Низкий-средний | High-security-нагрузки |
| **WASM** | Уровень языка | Минимальный | In-browser-агенты |

Большинство production-harness используют Docker для разработки и Firecracker (или аналог) для production. Ключевой принцип: **выполнение кода агента никогда не должно иметь доступа к файловой системе, сети или процессам хоста**.

## Санитизация ввода

Помимо guardrail на уровне tools, harness должен санитизировать ввод, чтобы снизить риск prompt injection:

```python
def sanitize_tool_result(result: str, max_length: int = 50_000) -> str:
    """Truncate and mark external content as untrusted."""
    if len(result) > max_length:
        result = result[:max_length] + "\n[TRUNCATED]"
    # Wrap in markers so the model knows this is external data
    return f"<tool_result>\n{result}\n</tool_result>"
```

Контент из внешних источников (веб-страницы, файлы пользователя, API-ответы) должен быть чётко размечен в context, чтобы модель отличала инструкции от данных.

## Частые ошибки

- **Никаких guardrails** — дефолт для большинства домашних harness. Норм для локальной разработки, катастрофично для production.
- **Guardrails только в промпте** — сказать модели «не удаляй файлы» — это не guardrail. Модель можно переписать через prompt injection. Настоящие guardrails обеспечиваются в коде, а не в тексте.
- **Слишком жёсткие разрешения** — агент, который не может сделать ничего полезного, не будет использоваться. Балансируйте security и utility.
- **Логирование запрещённых действий отсутствует** — понимать, что агент *пытался* сделать, но что заблокировали, критично для дебага и улучшения промптов.

## Что почитать

- [Simon Willison: Prompt Injection](https://simonwillison.net/series/prompt-injection/) — обстоятельная серия о threat-модели
- [Anthropic: Mitigating Prompt Injection](https://docs.anthropic.com/en/docs/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks) — практические паттерны защиты
