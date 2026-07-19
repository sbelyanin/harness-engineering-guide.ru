---
author: Harness Engineering Guide (RU)
title: "Open-Source LLM-стек: vLLM, Ollama, локальные модели в Harness"
section: practice
description: "Как заменить API-провайдеров на open-source inference: выбор модели, развёртывание vLLM/Ollama/TGI, оптимизация throughput, мониторинг и паттерны интеграции в harness для русскоязычных задач."
category: Practice
date: "2026-07-19"
---

# Open-Source LLM-стек: vLLM, Ollama, локальные модели в Harness

> **Главный инсайт:** Open-source LLM-стек сегодня решает 70% задач, которые 2 года назад требовали Claude/GPT. Но это **не бесплатный Claude** — это другой контракт: вы ownsаете latency, throughput, квантизацию и апгрейды моделей. Harness должен уметь работать с локальным endpoint’ом так же прозрачно, как с облачным, но с другим набором ошибок и метрик.

## Когда переходить на open-source

- **Данные не покидают периметр** — см. [On-Prem Harness](/guide/on-prem-harness)
- **Высокий стабильный трафик** — на 100M+ токенов/мес self-hosted дешевле в 3–10×
- **Специфичная задача** — fine-tuning на вашем corpus даёт выигрыш над general-purpose frontier
- **Регуляторика** — см. [compliance-152fz](/guide/compliance-152fz)

Не переходите, если:
- Трафик <1M токенов/мес — overhead на devops не окупится
- Нужен top-1 reasoning quality — frontier всё ещё впереди на сложных задачах
- Нет GPU-компетенции в команде — кластер надо поддерживать

## Слой 1. Выбор модели под harness

Для русскоязычных agent-задач критичны три свойства:

1. **Multilingual pretraining** — модель должна была увидеть ≥10% русского в corpus’е
2. **Native tool-calling** — без parsing-слоя
3. **Контекст ≥ 32K** — иначе memory summarization ломает инструкции

Таблица моделей, которые стабильно работают в русскоязычных harness (на момент написания — сверяйтесь с лидербордами):

| Модель | Параметры | RU-качество | Tool-calling | Контекст | Лицензия |
|-------|-----------|-------------|--------------|----------|----------|
| Qwen2.5-32B-Instruct | 32B | 🟢 | да | 128K | Apache 2.0 |
| Qwen2.5-14B-Instruct | 14B | 🟢 | да | 128K | Apache 2.0 |
| Qwen2.5-7B-Instruct | 7B | 🟡 | partial | 128K | Apache 2.0 |
| Llama-3.3-70B-Instruct | 70B | 🟡 | да | 128K | Llama 3.3 |
| Mistral-Nemo-12B-Instruct | 12B | 🟡 | да | 128K | Apache 2.0 |
| IlyaGPT-ru / Saiga-LLama-3 | 8B–70B | 🟢 | partial | 8K–32K | varies |
| T-lite-72B (T-Bank) | 72B | 🟢 | да | 32K | исследовательская |

**Эмпирическое правило:** для agent-loop берите минимум 14B. 7B-модели теряются на 3+ tool’ах и плохо держат длинные system prompt’ы.

## Слой 2. Inference-движки

### vLLM — high-throughput, recommended для production

Высокий throughput за счёт **PagedAttention** и continuous batching. Де-факто стандарт для GPU-кластеров.

```bash
# Запуск OpenAI-compatible server
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-32B-Instruct \
  --tensor-parallel-size 2 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.9 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --port 8000
```

Плюсы:
- OpenAI-compatible API — harness работает как с зарубежным провайдером
- Continuous batching — до 10× выше throughput на реальных нагрузках
- `--enable-auto-tool-choice` + parser — native function calling для поддерживаемых моделей

Минусы:
- Стартует 1–5 минут (загрузка весов, KV-cache preallocation)
- Память GPU нужно тюнить под нагрузку
- Update’ы модели требуют рестарта

### Ollama — простота, recommended для dev/single-node

Удобен для локальной разработки, прототипов, single-node deployments.

```bash
# Запуск
ollama serve

# В другом терминале
ollama run qwen2.5:32b
```

```python
# Harness-интеграция через OpenAI-compatible endpoint
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",  # не используется, но нужен для клиента
)
response = client.chat.completions.create(
    model="qwen2.5:32b",
    messages=[{"role": "user", "content": "Привет"}],
    tools=[...],  # поддерживается
)
```

Плюсы: простота, модель-реестр, GGUF-квантизация из коробки.
Минусы: ниже throughput (нет continuous batching), медленнее на высоких нагрузках.

### TGI (Text Generation Inference)

От HuggingFace. Удобен, если вы живёте в их экосистеме (Inference Endpoints, hub).

```bash
docker run --gpus all -p 8080:80 \
  -v $PWD/data:/data \
  ghcr.io/huggingface/text-generation-inference:latest \
  --model-id Qwen/Qwen2.5-32B-Instruct \
  --max-input-length 16000 \
  --max-total-tokens 32768
```

### Triton Inference Server

Если у вас смешанный workload (LLM + embeddings + classifiers на одном кластере) — Triton унифицирует deployment. Но порог входа выше.

## Слой 3. Квантизация — выбор под железо

| Формат | Размер (32B) | Loss качества | Скорость | Когда |
|--------|--------------|---------------|----------|-------|
| FP16 | ~64 GB | baseline | 1× | A100/H100 80GB |
| BF16 | ~64 GB | baseline | 1× | A100/H100 80GB |
| AWQ (4-bit) | ~18 GB | ~1–2% | 1.2–1.5× | A10G, L4, потребительские GPU |
| GPTQ (4-bit) | ~18 GB | ~2–3% | 1.1× | A10G, L4 |
| GGUF Q4_K_M | ~20 GB | ~2–4% | 0.7–1× (CPU-friendly) | Ollama, CPU/Mac |

Для русскоязычных задач loss от квантизации ощущается сильнее (модель уже на границе компетенции по русскому). **Берите 8-bit (AWQ-INT8 / FP8) для production**, 4-bit только для dev/prototyping.

## Слой 4. Harness-интеграция

### Provider abstraction

```python
from dataclasses import dataclass

@dataclass
class LocalLLMProvider:
    base_url: str
    model: str
    timeout_ms: int = 60000
    max_retries: int = 2

    async def complete(self, messages, tools=None, **kwargs):
        # Используем OpenAI-совместимый клиент
        async with httpx.AsyncClient(timeout=self.timeout_ms / 1000) as client:
            payload = {"model": self.model, "messages": messages, **kwargs}
            if tools:
                payload["tools"] = tools
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer local"},
            )
            resp.raise_for_status()
            return resp.json()
```

### Что отличается от облачного провайдера

- **Latency менее предсказуемая** — depends от вашей нагрузки и железа
- **Tool-calling парсинг** — vLLM требует указать `--tool-call-parser` под формат модели (hermes, mistral, llama)
- **Streaming работает, но без guaranteed finish_reason** — иногда отвечает `None` вместо `stop`
- **Rate limits = ваш GPU throughput** — нет 429 от облака, но есть OOM и queue buildup

### Failover локальный → облачный

```python
async def complete_with_fallback(messages, tools):
    try:
        return await local_provider.complete(messages, tools, timeout_ms=15000)
    except (httpx.TimeoutException, LocalOverloadedError):
        # Локальный кластер лёг — fallback в облако (если compliance позволяет)
        return await cloud_provider.complete(messages, tools)
```

## Слой 5. Мониторинг и эксплуатация

### Ключевые метрики

- **TTFT (Time To First Token)** — должен быть <1s для чат-сценариев, <3s для agent-loop
- **Throughput (tokens/sec/request)** — на 32B-модели на A100 должно быть 40–80 tok/sec
- **GPU utilization** — если <60%, значит batching настроен плохо
- **Queue depth** — глубина очереди continuous batching; >32 = деградация latency

### Health-check в harness

```python
async def local_llm_healthcheck() -> bool:
    try:
        result = await local_provider.complete(
            [{"role": "user", "content": "ping"}],
            timeout_ms=3000,
        )
        return bool(result.get("choices"))
    except Exception:
        return False
```

Вызывайте раз в 30 секунд, при падении переключайтесь на fallback.

## Слой 6. Русскоязычная специфика

- **Прогрейте модель русским corpus’ом через few-shot** в system prompt — иначе на длинных диалогах модель дрейфует в английский
- **Токенизатор должен поддерживать кириллицу эффективно** — Qwen2.5 и Llama 3 это делают хорошо, старые Llama 2 — плохо. См. [Cyrillic Tokenization](/guide/cyrillic-tokenization)
- **Fine-tuning** — если у вас есть domain corpus (тикетты, регламенты), LoRA-адаптер на 16K примеров поднимает quality на 15–30% над base

## Quickstart: docker-compose

Минимальный runnable-стек для локальной разработки: vLLM как inference-движок + OpenWebUI как ручной testbed. Не для production (нужны persistent volumes, monitoring, несколько worker'ов).

```yaml
# docker-compose.yml — локальный LLM-стек для harness-разработки
# Запуск: docker compose up -d
# Endpoint для harness: http://localhost:8000/v1/chat/completions

services:
  vllm:
    image: vllm/vllm-openai:latest
    ports:
      - "8000:8000"
    volumes:
      # Кэш весов модели переживает перезапуск контейнера
      - ~/.cache/huggingface:/root/.cache/huggingface
    environment:
      - HF_TOKEN=${HF_TOKEN}  # для gated-моделей (Qwen2.5 требует accept license)
    # Qwen2.5-32B-Instruct: хватает одной A100 (80GB) или двух A10G (24GB каждая)
    command: >
      --model Qwen/Qwen2.5-32B-Instruct
      --tensor-parallel-size 1
      --max-model-len 32768
      --gpu-memory-utilization 0.9
      --enable-auto-tool-choice
      --tool-call-parser hermes
      --served-model-name ru-harness-default
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              capabilities: [gpu]

  openwebui:
    image: ghcr.io/open-webui/open-webui:main
    ports:
      - "3000:8080"
    environment:
      - OPENAI_API_BASE_URL=http://vllm:8000/v1
      # OpenAI-совместимый клиент ходит в локальный vLLM
      - OPENAI_API_KEY=dummy  # vLLM по умолчанию не валидирует ключ
    volumes:
      - openwebui-data:/app/backend/data
    depends_on:
      - vllm

volumes:
  openwebui-data:
```

### Проверка

```bash
# 1. Подняли
docker compose up -d

# 2. Ждём загрузки весов (1–5 минут в зависимости от bandwidth)
docker compose logs -f vllm | grep "Application startup complete"

# 3. Smoke-test — должно вернуть JSON с choices
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ru-harness-default",
    "messages": [{"role": "user", "content": "Проверка: ответь «ок»."}],
    "max_tokens": 10
  }'

# 4. UI для ручных тестов: http://localhost:3000
```

### Что дальше

- **Production:** добавить Prometheus + Grafana для GPU monitoring (см. [Слой 5](#слой-5-мониторинг-и-эксплуатация))
- **Multi-node:** Ray-cluster вместо docker-compose (см. vLLM docs)
- **Air-gap:** скачать веса через `huggingface-cli download` на staging-машине, перенести в air-gap через подписанный артефакт (см. [On-Prem Harness](/guide/on-prem-harness))

## Антипаттерны

- **Брать 70B-модель на одну A10G** — квантизация сожмёт, но latency будет 5–15 sec/token, agent-loop умрёт
- **Полагаться на `tool-call-parser=auto`** — часто угадывает неверно, указывайте явно под модель
- **Стримить ответы без таймаута на каждый chunk** — локальная модель может «зависнуть» на длинной генерации
- **Деплоить без GPU monitoring** — out-of-memory на 32B = падение всего inference-слоя, harness получает connection refused

## Что почитать

- [Russian LLM в Harness](/guide/russian-llm-harness) — выбор русскоязычных моделей
- [On-Prem Harness](/guide/on-prem-harness) — air-gapped deployments
- [Tool System](/guide/tool-system) — проектирование tools под младшие модели
- [Cyrillic Tokenization](/guide/cyrillic-tokenization) — токен-бюджет под кириллицу
- [Eval Infrastructure Noise](/guide/eval-infrastructure) — почему локальное железо меняет метрики
