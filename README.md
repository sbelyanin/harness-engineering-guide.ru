<p align="center">
  <a href=«https://harness-guide.com»>
    <img src=«site/public/banner.png» alt=«Harness Engineering Guide» width=«100%» />
  </a>
</p>

<p align="center">
  <em>Практический гайд по созданию harness для AI-агентов — с реальными примерами кода, которые можно скопировать и запустить.</em>
</p>

<p align="center">
  <a href=«https://github.com/nexu-io/harness-engineering-guide/stargazers»><img src=«https://img.shields.io/github/stars/nexu-io/harness-engineering-guide?style=social» alt=«Stars»></a>
  <a href="LICENSE"><img src=«https://img.shields.io/badge/license-MIT-blue.svg» alt=«License»></a>
</p>

<p align="center">
  🌐 <b>Русскоязычное издание</b>
</p>

---

**Harness** — это runtime-оболочка, превращающая голую языковую модель в **Agent**: автономную систему, способную воспринимать окружение, принимать решения и выполнять действия за несколько шагов. Harness берёт на себя всё, что модель не может сделать сама: выполнение tools, управление memory, сборку context и обеспечение safety-границ.

Этот гайд охватывает harness engineering от первых принципов до production-паттернов, с реальным кодом в каждой статье.

> 📌 **Статус перевода:** переведены все 25 статей гайда, changelog и skill abuse-hunter. Текущий фокус — финальная вычитка и независимое развитие русскоязычного издания. См. [`ROADMAP.md`](ROADMAP.md). Оригинал: [nexu-io/harness-engineering-guide](https://github.com/nexu-io/harness-engineering-guide).
>
> История изменений — в [`changelog/`](changelog/).

---

## Getting Started / Введение

| Тема | Описание |
|-------|-------------|
| [Что такое Harness?](guide/what-is-harness.md) | Концепция за 3 минуты. Как модель превращается в агента. Harness vs. framework vs. runtime. |
| [Ваш первый Harness](guide/your-first-harness.md) | Рабочий harness на 50 строках Python. Полный код — копируйте и запускайте. |
| [Harness vs. Framework](guide/harness-vs-framework.md) | Когда брать сырой harness, а когда — LangChain/CrewAI. Дерево решений + сравнение кода. |

## Core Concepts / Базовые концепции

| Тема | Описание |
|-------|-------------|
| [Agentic Loop](guide/agentic-loop.md) | Цикл think → act → observe. Бюджеты ходов, параллельные tool-вызовы, обнаружение зацикливания, streaming. |
| [Tool System](guide/tool-system.md) | Реестр tools, статическая vs. динамическая загрузка, MCP-протокол, качество описаний. |
| [Memory & Context](guide/memory-and-context.md) | Сборка context, управление session, двухуровневая memory (дневные логи + долгосрочная). Паттерны AGENTS.md и MEMORY.md. |
| [Guardrails](guide/guardrails.md) | Модели разрешений, trust-границы, sandboxing, защита от prompt injection. |

## Practice / Практика

| Тема | Описание |
|-------|-------------|
| [Context Engineering](guide/context-engineering.md) | Сборка по приоритетам, три линии защиты при сжатии, токен-бюджет. |
| [Sandbox](guide/sandbox.md) | Конфигурации Docker и Firecracker, сетевая изоляция, ограничения файловой системы. |
| [Skill System](guide/skill-system.md) | Упаковка skills, загрузка по требованию, формат SKILL.md, thin harness + thick skills. |
| [Sub-Agent](guide/sub-agent.md) | Паттерн Leader-Worker, общение через файлы, изоляция session, параллельное выполнение. |
| [Error Handling](guide/error-handling.md) | Классификация ошибок, стратегии retry, graceful degradation, checkpoint/resume. |
| [Multi-Agent Orchestration](guide/multi-agent-orchestration.md) | Паттерны оркестрации (pipeline, fan-out, supervisor), изоляция context, реальные примеры (Multica, Paseo, OpenClaw). |
| [Scheduling & Automation](guide/scheduling-and-automation.md) | Cron, heartbeats, event-триггеры. Targeting session, доставка, сравнение LangSmith vs harness-native. |
| [Long-Running Harness Design](guide/long-running-harness.md) | Context anxiety, bias самооценки, reset vs compaction, архитектура generator-evaluator по мотивам GAN. |
| [Managed Agents Architecture](guide/managed-agents-architecture.md) | Разделение brain/hands/session, pets vs cattle, изоляция кредов, улучшения TTFT. |
| [Eval Infrastructure Noise](guide/eval-infrastructure.md) | Конфигурация ресурсов сдвигает оценки бенчмарка на 6 п.п. Стратегия floor+ceiling. |
| [Classifier-Based Permissions](guide/classifier-permissions.md) | Заменить approval fatigue модельными классификаторами. Двухслойная защита, четыре threat-модели. |
| [Eval Awareness](guide/eval-awareness.md) | Когда агенты распознают, что их тестируют. Novel contamination, multi-agent amplification, защиты harness. |
| [Agent Teams](guide/agent-teams.md) | 16 параллельных Claude собрали C-компилятор на 100K строк. Ralph-loop, git-координация, GCC-as-oracle. |
| [Initializer + Coding Agent Pattern](guide/initializer-coding-pattern.md) | Двухфазный harness для долгоиграющих агентов. Feature list JSON, startup ritual, clean state commit. |
| [Russian LLM в Harness](guide/russian-llm-harness.md) | Особенности построения harness под русскоязычные модели: токенизация, tool-calling, локальный контекст. |
| [On-Prem Harness: air-gapped](guide/on-prem-harness.md) | Запуск harness в изолированном контуре: локальный inference, vending tools, подписанные bundle’ы, аудит. |
| [YandexGPT и GigaChat](guide/yandexgpt-and-gigachat.md) | Подключение российских коммерческих моделей: IAM-токены Yandex, OAuth GigaChat, adapter над сообщениями, failover. |
| [Open-Source LLM-стек](guide/open-source-llm-stack.md) | vLLM/Ollama/TGI как замена API-провайдерам: квантизация, throughput, мониторинг, failover. |
| [Cyrillic Tokenization](guide/cyrillic-tokenization.md) | Токен-экономика русского текста: измерение penalty, пересчёт budget, bilingual strategy. |
| [Compliance: 152-ФЗ](guide/compliance-152fz.md) | Harness под персональные данные: классификация ПДн, цели обработки, pseudonymization, право на удаление, журнал доступа. |

## Reference / Справочник

| Тема | Описание |
|-------|-------------|
| [Сравнение реализаций](guide/comparison.md) | Параллельное сравнение OpenClaw, Claude Code, Codex, Cline, Aider, Cursor. |
| [Глоссарий](guide/glossary.md) | Ключевые термины с определениями. |

## Showcase / Кейсы

| Тема | Описание |
|-------|-------------|
| [Релиз нашего Windows-клиента](guide/nexu-windows-packaging.md) | Время сборки 15мин→4мин, установки 10мин→2мин. Как мы перестроили pipeline упаковки Electron. |
| [Охота на ghost-аккаунты](guide/ghost-account-hunting.md) | 1000+ ghost-аккаунтов истощили платформу за 15 дней. Полный post-mortem. |

---

## Как контрибьютить

1. Зайдите в [**Issues → New Issue**](https://github.com/nexu-io/harness-engineering-guide/issues/new/choose)
2. Выберите **«📬 Submit a Resource»**
3. Заполните заголовок, URL и почему это релевантно

Либо отправьте PR напрямую — см. [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Сообщество

- 💬 **GitHub Discussions** — [Присоединиться к обсуждению](https://github.com/nexu-io/harness-engineering-guide/discussions)
- 🐦 **Twitter / X** — [@nexudotio](https://x.com/nexudotio)

---

## О проекте

Перевод и адаптация проекта [Nexu](https://github.com/nexu-io) — open-source платформы Claude Co-worker & Managed Agent.

План перевода и развития — в [`ROADMAP.md`](ROADMAP.md).

## Лицензия

[MIT License](LICENSE)

---

Если гайд оказался полезен, поставьте ⭐ — это помогает проекту расти.

```
@misc{nexu_harness-engineering-guide_2026,
  author = {Nexu Team},
  title = {Harness Engineering Guide},
  year = {2026},
  publisher = {GitHub},
  howpublished = {\url{https://github.com/nexu-io/harness-engineering-guide}}
}
```
