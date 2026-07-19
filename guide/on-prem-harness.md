---
author: Harness Engineering Guide (RU)
title: "On-Prem Harness: запуск в air-gapped среде"
section: practice
description: "Как построить harness, который работает без доступа к публичным API frontier-моделей: локальный inference, изолированный tool-реестр, offline-обновления и аудит под enterprise-требованиями."
category: Practice
date: "2026-07-19"
---

# On-Prem Harness: запуск в air-gapped среде

> **Главный инсайт:** Большинство руководств по harness подразумевают вызов Claude/GPT через интернет. В корпоративном контуре data-сегмент часто полностью изолирован: ни внешних API, ни pip-зеркал, ни телеметрии. Harness, который «просто работает» в облаке, в air-gap'е требует пересборки четырёх слоёв: model serving, tool registry, sandbox и обновлений.

## Когда это нужно

Air-gapped harness — не мода, а требование. Типовые сценарии:

- **Финансовый сектор** — данные клиентов не покидают периметр, моделей на внешних API нет
- **Госсектор и ОПК** — класс защищённости, аттестация ФСТЭК, запрет на исходящий трафик
- **Промышленность** — SCADA/АСУ ТП в изоляции, интеграция с локальными historian и MES
- **Медицина** — врачебная тайна, 152-ФЗ, региональные ограничения хранения

В этих контурах frontier-модель через HTTPS недоступна по определению. Значит, harness должен работать на локальном inference.

## Архитектура air-gapped harness

```
┌─────────────────────── ВНЕШНИЙ КОНТУР (staging) ───────────────────────┐
│                                                                         │
│  Internet ──→ bastion (sign-only) ──→ artifact-registry                 │
│              (только исходящий             │                            │
│               SSH/HTTPs, логируется)       │                            │
│                                            ▼                            │
│                                 ┌───────────────────┐                   │
│                                 │ model-weights-repo│  (подписанные)    │
│                                 │ package-mirror    │  (apt/pypi proxy) │
│                                 └───────────────────┘                   │
│                                            │                            │
└────────────────────────────────────────────┼────────────────────────────┘
                                             │ односторонний transfer
                                             │ (sneaker-net / data-diode)
                                             ▼
┌─────────────────────── ВНУТРЕННИЙ КОНТУР (air-gapped) ──────────────────┐
│                                                                         │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │                    DATA-СЕГМЕНТ (no internet)                    │  │
│   │                                                                  │  │
│   │  ┌──────────┐    ┌──────────────┐    ┌────────────────────┐      │  │
│   │  │ user UI  │───▶│   harness    │───▶│  tool registry     │      │  │
│   │  │ / web    │    │  (agent-loop)│    │  (internal-only)   │      │  │
│   │  └──────────┘    └──────┬───────┘    └─────────┬──────────┘      │  │
│   │                         │                       │                 │  │
│   │                         ▼                       ▼                 │  │
│   │                 ┌──────────────┐        ┌──────────────┐          │  │
│   │                 │  vLLM cluster│        │  sandbox     │          │  │
│   │                 │  (GPU, RU    │        │  (gVisor/FD) │          │  │
│   │                 │   models)    │        │              │          │  │
│   │                 └──────────────┘        └──────────────┘          │  │
│   │                         │                       │                 │  │
│   │                         ▼                       ▼                 │  │
│   │                 ┌──────────────────────────────────────┐          │  │
│   │                 │  primary DB (ПДн, РФ-локация)         │          │  │
│   │                 │  audit-log (хеши, не payload)         │          │  │
│   │                 │  memory-store (TTL-управляемый)       │          │  │
│   │                 └──────────────────────────────────────┘          │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │                 MANAGEMENT-СЕГМЕНТ (read-only к data)            │  │
│   │                                                                  │  │
│   │   Prometheus ◀── exporters (Grafana для read)                    │  │
│   │   audit-viewer (only хеши + метаданные)                          │  │
│   └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Ключевые свойства:**

- **Односторонний transfer** — обновления идут из staging в air-gap через подписанные артефакты (data-diode или sneaker-net). Обратного канала нет.
- **Data-сегмент полностью изолирован** — ни DNS, ни исходящих HTTPS, ни NTP из internet. Только внутренние сервисы.
- **Management-сегмент** имеет read-only доступ к audit-log и метрикам — для SOC/DPO без возможности модифицировать данные.
- **Audit-log пишет хеши** — не сами ПДн, что позволяет вести журнал без расширения perimeter ПДн.

## Слой 1. Model serving внутри периметра

### Развёртывание inference

Вместо `https://api.anthropic.com` harness указывает на внутренний endpoint. Типовые движки:

- **vLLM** — high-throughput, OpenAI-compatible API, PagedAttention. Де-факто стандарт для GPU-кластеров
- **TGI (Text Generation Inference)** — от HuggingFace, удобен для шаблонов чата
- **Ollama** — простота для single-node, ниже throughput
- **Triton Inference Server** — для смешанных workloads (LLM + embedding + классификаторы)

```yaml
# Концептуальное определение провайдера модели
provider: openai-compatible
base_url: "http://llm-vip.internal.corp:8080/v1"
api_key_env: "LLM_INTERNAL_TOKEN"   # ротируется локальным vault
model: "Qwen/Qwen2.5-32B-Instruct"
timeout_ms: 60000
retries: 2
fallback:
  - base_url: "http://llm-backup.internal.corp:8080/v1"
    model: "Qwen/Qwen2.5-14B-Instruct"   # легче, но быстрее — на случай деградации
```

### Подбор модели под harness

Air-gapped не означает «любая модель». Для agent-loop критичны:

1. **Native tool-calling** — иначе придётся строить parsing layer и терять надёжность
2. **Контекст ≥ 32K** — иначе memory summarization съест инструкцию
3. **Стабильный формат ответа** — без случайных `<think>`-обёрток, ломающих парсер

Если модель не держит tool-calling, harness должен явно переключаться в **text-mode** с шаблоном-экстрактором: модель пишет JSON-блок в fenced code, harness его парсит. См. [Tool System](/guide/tool-system).

## Слой 2. Tool registry без внешних MCP

В облаке агент может дотянуться до сотни SaaS-API и публичных MCP-серверов. В air-gap'е это всё отрезано.

### Что меняется

- **Tools живут рядом с harness** — реестр описан локально, без discovery по сети
- **Зависимости vendored** — все Python-пакеты tools заморожены в артифакте сборки
- **HTTP-tools только на internal host'ы** — любые внешние URL’ы отклоняются guardrail'ом

```python
def allowed_tool_endpoint(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname
    # Разрешаем только внутренние суффиксы; всё остальное блокируется
    return host is not None and (
        host.endswith(".internal.corp")
        or host.endswith(".local")
        or host == "localhost"
    )
```

### Локальный каталог tools

Вместо динамической подгрузки skills из GitHub — статический manifest, собранный на CI build-машине с доступом в интернет, и подписанный. См. [Skill System](/guide/skill-system) про упаковку.

## Слой 3. Sandbox и сеть

[Гайд по Sandbox](/guide/sandbox) описывает Docker/Firecracker. В air-gap'е:

- **Базовые образы тянутся из внутреннего registry**, не из Docker Hub
- **Egress = deny by default** — сетевая политика разрешает только целевые host'ы
- **Volume-mount’ы только для утверждённых директорий** — agent не должен иметь доступ ко всему data-сегменту

```python
container_run_config = {
    "image": "registry.internal.corp/sandbox/python:3.12-slim",
    "network": "agent-net-isolated",        # только internal DNS
    "memory": "2g",
    "cpus": 2.0,
    "read_only_root": True,
    "allowed_paths": ["/workspace", "/data/readonly"],
    "ephemeral": True,                       # убивается после task
}
```

## Слой 4. Обновления и секреты

Воздушный разрыв ломает привычные «`pip install`/`docker pull` по требованию». Всё должно приезжать через **data-staging** — машину-посредник, которая валидирует и протаскивает артифакты в закрытый контур.

### Артифактный конвейер

1. На build-машине (с интернетом) собирается bundle: веса модели, Python-зависимости, Docker-образы, skill-пакеты
2. Bundle подписывается (sigstore / GPG) и кладётся на переносимый носитель или staging-канал
3. На стороне air-gap’а подпись проверяется, bundle разворачивается в локальный registry и model-store
4. Harness при старте сверяет хеши с подписанным manifest

### Секреты

- **Локальный vault** (HashiCorp Vault, Sensormap, файловые секреты с шифрованием)
- **Никаких секретов в env-переменных контейнера** в открытом виде — только через secret-mount с временным доступом
- **Аудит доступа** — каждый запрос агента к кредам логируется

## Слой 5. Аудит и журнал

В регулируемых контурах лог — это не debugging nicety, а юридическое требование.

- **Каждый tool-call** записывается: input, output, timestamp, initiator session
- **Каждый промпт к модели** — в неизменяемый лог (WORM-хранилище)
- **PII-фильтрация** перед записью: если агент обработал персональные данные, в логе остаются только хеши/маски

```python
def log_tool_call(call: ToolCall, result: ToolResult) -> None:
    audit_logger.write({
        "ts": datetime.utcnow().isoformat(),
        "session": call.session_id,
        "tool": call.name,
        "input_hash": sha256(mask_pii(call.input)),
        "output_hash": sha256(mask_pii(result.output)),
        "status": result.status,
        # payload не пишем — только хеши + метаданные
    })
```

См. [Guardrails](/guide/guardrails) про trust-границы и [compliance-152fz](/guide/compliance-152fz) про обработку ПДн *(статья в работе)*.

## Антипаттерны

- **Пробросить один VPN-тоннель к публичному API** — ломает изоляцию, ломает аттестацию, ловится на аудите
- **Хранить веса модели в Git LFS** — артефакт тонкий, легко подменить; нужен подписанный registry
- **Запускать agent-loop от root** — любой prompt injection становится полноценным RCE
- **Обновлять пакеты «по требованию»** — в air-gap’е это просто не сработает; только через staging

## Что почитать

- [Что такое Harness?](/guide/what-is-harness) — базовая архитектура
- [Sandbox](/guide/sandbox) — изоляция выполнения tools
- [Guardrails](/guide/guardrails) — trust-границы и модели разрешений
- [Russian LLM в Harness](/guide/russian-llm-harness) — специфика русскоязычных моделей, актуальная для on-prem развёртываний
