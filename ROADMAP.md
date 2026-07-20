# ROADMAP — Harness Engineering Guide (RU)

Русскоязычное издание [harness-engineering-guide](https://github.com/nexu-io/harness-engineering-guide).
Цель — полный перевод гайда на русский с последующим самостоятельным развитием проекта.

---

## Принятые решения

| Решение | Выбор |
|---------|-------|
| Языковая архитектура | **Standalone-русский**. Русский — единственный язык сайта. Маршруты `/`, `/guide/[slug]`, `/changelog` без языкового префикса. |
| Технические термины | **Оставлять на английском** (Harness, Agent, Context, Tool, Sandbox, Guardrails, Skill, Sub-Agent, Loop, Memory, Session и т.д.) — по образцу китайской версии. Переводится только связующая проза. |
| Наполнение | **Перевод + расширение**. Сначала точный перевод всех статей оригинала, затем независимый рост (новые разделы/статьи под русскоязычную аудиторию). |

## Конвенция перевода

- **Frontmatter** (`---\nauthor: Nexu\n---`) — сохраняется как есть.
- **Заголовки и проза** — переводятся на русский.
- **Технические термины** — остаются на английском, при первом упоминании можно добавить русский аналог в скобках: «Harness (оболочка)».
- **Код, ASCII-диаграммы, таблицы** — структура и содержимое сохраняются; переводятся только текстовые подписи/комментарии внутри по необходимости.
- **Ссылки** — сохраняются; переводится текст анкора.
- **Тон** — практичный, технически точный, без кальки с английского синтаксиса.

## Структура проекта (целевая)

```
harness-engineering-guide.ru/
├── ROADMAP.md            ← этот файл
├── README.md             ← русское оглавление
├── CONTRIBUTING.md       ← русский
├── LICENSE               ← MIT (без изменений)
├── .gitignore
├── guide/                ← русские статьи (25+)
├── changelog/            ← русский changelog
├── skills/               ← навыки (перевод README + пакеты)
├── site/                 ← Next.js, standalone-русский
│   ├── app/              ← /  /guide/[slug]  /changelog  (без /ru, /zh)
│   ├── components/       ← без LangSwitcher, без isZh
│   ├── lib/              ← guide-data.ts (один заголовок), content.ts
│   ├── scripts/sync-content.sh
│   └── public/
└── .github/              ← issue templates, workflows
```

Отличия от оригинала:
- Нет `zh-guide/`, `zh-changelog/`, `README.zh-CN.md`.
- Нет маршрутов `/zh/*` и компонента `LangSwitcher`.
- `lib/guide-data.ts` хранит один заголовок (`title`) вместо `title`+`zhTitle`.
- `site/app/zh/` целиком удалён.

---

## Этап 1 — Фундамент ✅

Цель: рабочий скелет проекта + эталонная статья + проверка pipeline'а.

- [x] Корневые файлы: `LICENSE`, `.gitignore`, `CONTRIBUTING.md` (перевод), `README.md` (русское оглавление)
- [x] Скелет `site/`: копия + адаптация под standalone-русский (убраны `/zh`, `LangSwitcher`, `isZh`)
- [x] Перевести `guide/what-is-harness.md` — эталон конвенции
- [x] Проверить сборку `next build` — SSG работает

## Этап 2 — Getting Started + Core Concepts ✅

- [x] `guide/your-first-harness.md`
- [x] `guide/harness-vs-framework.md`
- [x] `guide/agentic-loop.md`
- [x] `guide/tool-system.md`
- [x] `guide/memory-and-context.md`
- [x] `guide/guardrails.md`

> Проверка сборки после этапа 2: все 7 страниц генерируются как SSG без ошибок TypeScript.

## Этап 3 — Practice (14 статей) ✅

- [x] `guide/context-engineering.md`
- [x] `guide/error-handling.md`
- [x] `guide/skill-system.md`
- [x] `guide/sandbox.md`
- [x] `guide/sub-agent.md`
- [x] `guide/long-running-harness.md`
- [x] `guide/managed-agents-architecture.md`
- [x] `guide/eval-infrastructure.md`
- [x] `guide/eval-awareness.md`
- [x] `guide/classifier-permissions.md`
- [x] `guide/scheduling-and-automation.md`
- [x] `guide/initializer-coding-pattern.md`
- [x] `guide/multi-agent-orchestration.md`
- [x] `guide/agent-teams.md`

> Проверка сборки после этапа 3: 21 страница гайда генерируется как SSG.

## Этап 4 — Reference + Showcase (4 статьи) ✅

- [x] `guide/comparison.md` (~119 строк)
- [x] `guide/glossary.md` — уже переведён
- [x] `guide/nexu-windows-packaging.md` (~123 строки)
- [x] `guide/ghost-account-hunting.md` (~151 строка)

## Этап 5 — Changelog + Skills + финализация README ✅

- [x] Перевести `changelog/2026-04-15.md`, `2026-04-16.md`, `2026-04-19.md`
- [x] Перевести `skills/README.md` (+ пакет `skills/abuse-hunter/`)
- [x] Финальный `README.md` с полным оглавлением, бейджами и сообществом
- [x] `.github/` — issue templates, workflows (адаптация ссылок)

## Этап 6 — Финальная проверка ✅

- [x] `next build` без ошибок (SSG: 25 guide + changelog + главная)
- [x] Проверка всех внутренних ссылок в гайде
- [x] Проверка SEO-метаданных (`layout.tsx`, `page.tsx`, frontmatter titles)
- [x] Сверка заголовков `guide-data.ts` с frontmatter/H1 в guide-статьях

> Этап 7 — см. архивный раздел ниже. Практически завершён (Track A/C/D ✅, B6 — по запросам сообщества).

## Этап 8 — Зрелость проекта: features + quality gates ✅

Цель: превратить функциональный сайт в зрелый продукт — улучшить UX чтения, добавить автоматические защиты от регрессий, поднять SEO-видимость, углубить ключевой контент. Работа ведётся параллельно по **четырём трекам**.

### 🧩 Track E — Site features (UX чтения и discovery) ✅

- [x] **E1.** Reading-time в ArticleLayout (`computeReadingTime` в content.ts, ~150 wpm, NB: вырезает code-блоки).
- [x] **E2.** Блок «Связанные статьи» (`getRelatedArticles` в guide-data.ts: +5 за ту же section, +1 за общий title-токен).
- [x] **E3.** RSS-фид `/feed.xml` (RSS 2.0 + Atom self-link; только `ru-` prefix; autodiscovery в layout metadata).
- [x] **E4.** Client-side поиск: `/search.json` (static, ~200KB на 31 статью) + `SearchDialog` (zero-dep fuzzy substring, keyboard nav ↑↓/Enter/Esc, shortcut `/` или `Cmd/Ctrl+K`).
- [x] **E0.** *(уже было)* TOC-сайдбар для длинных статей через `TableOfContents`.

### 🛡 Track F — Quality gates (защита от регрессий) ✅

Самый высокий agent-value: фиксирует конвенции STYLE.md и архитектурные invariant'ы.

- [x] **F1.** `site/scripts/check_frontmatter.py` — валидатор frontmatter (`title` + `section` + `author` обязательны; `section` ∈ enum).
- [x] **F2.** `site/scripts/check_registry.py` — детект registry drift: `guide-data.ts` ↔ `guide/*.md`. Информационно сообщает о расхождениях `frontmatter.title` ↔ sidebar-title (intended — sidebar короткий).
- [x] **F3.** `site/scripts/check_links.py` — линкер внутренних ссылок: `/guide/<slug>` → `guide/<slug>.md`, относительные пути, README/ROADMAP cross-links.
- [x] **F4.** `site/scripts/check_style.py` — STYLE.md linter: ASCII `"..."` в prose, русские транслитерации EN терминов, NBSP в исходниках. State-machine парсер code-fences (CommonMark-совместимый, nested fences через ≥4 backticks).
- [x] **F5.** `.github/workflows/quality.yml` — запуск F1-F4 на PR + push в main. Runner: `site/scripts/run-quality-gates.sh`.
- [x] **Попутно фиксы реальных багов**, найденных чекерами: `ghost-account-hunting.md` без `author`; 4× кириллических вариантов слова «Framework» в `glossary.md`/`harness-vs-framework.md`; nested code-fence в `yandexgpt-and-gigachat.md` (требует 4-backtick outer fence по CommonMark).

### 📈 Track G — SEO & discovery

- [x] **G0.** *(уже было)* `app/sitemap.ts`, `app/robots.ts`.
- [x] **G1.** Sitemap: добавлен `/community`, `lastModified` из frontmatter.date или fs.mtime, приоритеты + changeFrequency, anchor-ссылки для changelog.
- [x] **G2.** JSON-LD `Article` schema в `<script type="application/ld+json">` на guide-страницах.
- [x] **G3.** OG-изображения: `banner.png` подключён в `layout.tsx` (site-wide default) и в guide-страницах (`openGraph.images` + `twitter.images` с alt = заголовок статьи).
- [x] **G4.** `alternates.canonical` в `generateMetadata` для guide-страниц + OpenGraph/Twitter cards.

### 📚 Track H — Content depth (расширение ключевых статей) ✅

По приоритету влияния на читателя:

- [x] **H1.** `guide/russian-llm-harness.md` — эталонная `harness.toml` (multi-provider failover, RU token budget, text-mode fallback, pdn_filter).
- [x] **H2.** `guide/yandexgpt-and-gigachat.md` — таблица сравнения моделей под harness-задачи (6 моделей × context/tools/latency/strengths/weaknesses).
- [x] **H3.** `guide/open-source-llm-stack.md` — `docker-compose.yml` quickstart (vLLM + OpenWebUI, GPU deployment, smoke-test).
- [x] **H4.** `guide/compliance-152fz.md` — заполненный пример аудита для типового support-бота + sample journal entry.
- [x] **H5.** `guide/on-prem-harness.md` — ASCII-диаграмма air-gapped deploy (staging/data/management сегменты, односторонний transfer).

---

## Этап 9 — Observability + production-readiness

Цель: дать читателю полный цикл запуска harness в production — от instrumenting модели до runbook'а на дежурстве. LLM-системы принципиально недетерминированы, поэтому классические методы мониторинга (RED, USE) нужно адаптировать. Работа ведётся по **четырём трекам**.

### 📊 Track I — Книги: observability для harness

Пять статей покрывают весь цикл наблюдаемости — от базовой инструментации до postmortem'а.

- [x] **I1.** `guide/observability.md` (section: core-concepts) — введение: почему LLM ≠ regular service, три кита (metrics/logs/traces), стоимость «слепых зон», связь с eval-infrastructure.
- [x] **I2.** `guide/harness-metrics.md` (section: practice) — RED для harness: Rate (requests/s, tokens/s), Errors (по классам: model, tool, guardrail), Duration (LLM p50/p95/p99, tool latency). Naming conventions, units, гистограммы. Что НЕ измерять.
- [x] **I3.** `guide/llm-tracing.md` (section: practice) — distributed tracing: OpenTelemetry GenAI semantic conventions, span attributes (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.*`), context propagation через agent-loop, стоимость trace'ов (sampling).
- [x] **I4.** `guide/alerting-and-slo.md` (section: practice) — SLO для harness (success rate, latency p99, cost per session), error budget, multi-window multi-burn-rate alerts, oncall routing.
- [x] **I5.** `guide/incident-runbook.md` (section: practice) — типовые инциденты (model outage, tool deprecation, prompt injection detected, cost spike, context-window exhaustion), runbook для каждого, postmortem template.

### 🛠 Track J — Skills

- [x] **J1.** `skills/harness-metrics-exporter/` — Python-скрипт (stdlib-only), парсит логи harness (JSON-lines) → экспортирует Prometheus exposition format. Готов к `node_exporter textfile collector`.
- [x] **J2.** `skills/incident-postmortem/` — шаблон постмортема (markdown) с заготовкой структуры (timeline, impact, root cause, action items), auto-fill из trace ID если есть.

### 🧪 Track K — Инженерные улучшения сайта

- [ ] **K1.** Страница `/metrics` — публичный статус проекта: бейджи CI, последняя сборка, число статей/skills, размер бандла. Служит «dogfooding»-примером: вот так выглядит observability даже у docs-сайта.

### 🔁 Track L — Поддержка и cross-cutting

- [ ] **L1.** Обновить `README.md` — упомянуть observability-статьи.
- [ ] **L2.** Обновить `skills/README.md` — новые skills (J1, J2).
- [ ] **L3.** Создать `changelog/ru-YYYY-MM-DD.md` по завершении Этапа 9.
- [ ] **L4.** Опционально: перекрёстные ссылки из существующих статей (eval-infrastructure, error-handling, long-running-harness).

---



Цель: превратить RU-издание из перевода в самостоятельный проект, ориентированный на русскоязычную аудиторию. Работа ведётся параллельно по **четырём трекам** (A → B/C/D), каждый трек разбит на подзадачи.

### 🔍 Track A — Аудит и вычитка переводов (приоритет, фундамент)

Привести в порядок то, что уже есть, до того как накапливать новый объём.

- [x] **A1.** Проверить качество переводов: английский в prose, остатки непереведённого. → *Чисто.*
- [x] **A2.** Проверить все внутренние ссылки (README → guide, guide ↔ guide, ROADMAP). → *Все резолвятся.*
- [x] **A3.** Сверка заголовков `frontmatter.title ↔ H1 ↔ guide-data.ts`. → *Расхождения задокументированы ниже.*
- [x] **A4.** Выровнять frontmatter во всех статьях: добавить `title` + `section` (где отсутствует) — единый стиль, надёжный fallback без H1.
- [x] **A5.** Убрать дублирующие `# H1` mid-документа в `scheduling-and-automation.md` → превратить в `## H2` (3 вхождения). *(Оказались YAML/Python-комментариями внутри кодовых блоков — ложная тревога. Вместо этого добавлен недостающий body H1 для единообразия с остальными 25 статьями.)*
- [x] **A6.** Унифицировать русскую транслитерацию терминов (глоссарий как эталон): `фреймворк→framework`, `пайплайн→pipeline`, `фича→feature`, `фидбек→feedback`, `дашборд→dashboard`, `бэкенд→backend`, `хэш→хеш`. Канон зафиксирован в [`STYLE.md`](STYLE.md).
- [x] **A7.** Прогнать тёмные углы: ASCII `"..."`→`«ёлочки»` (23 замены), NBSP-расстановка через `typographRussian()` в `content.ts` (HTML-level, code-блоки пропускаются).

### 📝 Track B — Новые RU-оригинальные статьи

Статьи, которых нет в upstream, под реалии русскоязычной аудитории.

- [x] `guide/russian-llm-harness.md` — harness под русскоязычные модели (эталон RU-статьи).
- [x] **B1.** `guide/on-prem-harness.md` — запуск harness в air-gapped/on-prem среде (частый запрос enterprise-RU).
- [x] **B2.** `guide/yandexgpt-and-gigachat.md` — интеграция YandexGPT / GigaChat / GigaChat MAX как провайдеров в harness.
- [x] **B3.** `guide/open-source-llm-stack.md` — vLLM + Ollama + локальные модели как замена API-провайдерам.
- [x] **B4.** `guide/cyrillic-tokenization.md` — токен-экономика русского текста, ценовая оптимизация под RU-локализацию.
- [x] **B5.** `guide/compliance-152fz.md` — harness + 152-ФЗ: где хранить ПДn, логирование, право на удаление.
- [ ] **B6.** Кейсы RU-команд (по мере поступления).

### 🧰 Track C — Расширение skills-пакетов

Готовые skills с `SKILL.md` + скрипты, ориентированные на русскоязычные задачи.

- [x] `skills/abuse-hunter/` — перевод оригинального skill.
- [x] **C1.** `skills/ru-doc-summarizer/` — саммаризация русскоязычных документов (ГОСТы, регламенты, длинные треды) + chunker на Python.
- [x] **C2.** `skills/cyrillic-log-analyzer/` — разбор логов/текстов с перемешанной кодировкой/транслитом: 4 подкоманды (analyze/fix/translit/layout), mojibake UTF-8↔CP1251/Latin-1, 3 схемы транслитерации, layout switch.
- [x] **C3.** `skills/152fz-audit/` — аудит chat-логов агента на наличие ПДn, попавших в context (regex + pseudonymization, Luhn/ИНН-check).
- [x] **C4.** Расширить `skills/README.md` таблицей всех новых skills (4 пакета: 1 перевод + 3 RU-оригинала).

### 🔄 Track D — Свежий RU-changelog + сообщество

Свой changelog русскоязычного издания (отдельно от перевода upstream), страницы сообщества.

- [x] **D1.** Ввести префикс `ru-` для дат RU-издания в `changelog/` (отделить от upstream-переводов): `changelog/ru-2026-07-19.md`.
- [x] **D2.** Страница `/community` на сайте (или раздел в README): как контрибьютить, чат, связь.
- [x] **D3.** `CONTRIBUTING.md` — расширить раздел про добавление RU-оригинальных статей (не только переводы).
- [x] **D4.** Лента «что нового в RU-издании» на главной странице сайта (фильтр по slug-префиксу `ru-`, последние 5).

---

## Подзадачи Этапа 7 — порядок выполнения

1. **Track A (A4–A7):** вычитка и стандартизация — фундамент перед ростом объёма.
2. **Track B (B1):** первая новая RU-оригинальная статья после `russian-llm-harness`.
3. **Track C (C1):** первый новый RU-оригинальный skill.
4. **Track D (D1+D2):** запуск собственного changelog + страница сообщества.
5. **Далее:** параллельный рост по B/C/D с ревизией после каждого набора из 3–5 единиц.

## Состояние аудита (этап A1–A3)

- **A1 (английский в prose):** найден только в коде, JSON, ASCII-диаграммах и умышленно цитируемых промптах — соответствует конвенции.
- **A2 (ссылки):** все ссылки в `README.md`, `ROADMAP.md` и cross-link'и в `guide/` резолвятся.
- **A3 (заголовки):** выявлены две некритичные аномалии:
  - `scheduling-and-automation.md`: 3 лишних `# H1` mid-документа (строки 188, 281, 308) — унаследовано от upstream, исправляется в A5.
  - `comparison.md`: FM-title «Сравнение реализаций» vs H1 «Сравнение основных реализаций Harness» — сайт использует FM-title (content.ts:132), отображение корректно.
  - 18 статей имеют frontmatter только с `author: Nexu` (без `title`) — унаследовано от upstream, fallback на H1 работает, унификация в A4.

---

## Прогресс

- Этап 1–6: **завершены** ✅ (полный перевод 25 статей оригинала + changelog + skills + .github)
- Этап 7: **практически завершён** 🔄 (Track A/C/D ✅, B6 — по запросам сообщества)
- Этап 8: **завершён** ✅ (все 4 трека: E, F, G, H)
  - Track E (site features): **5/5 ✅** (reading time, related, RSS, search, TOC)
  - Track F (quality gates): **5/5 ✅** (F1-F5 + попутные фиксы контента)
  - Track G (SEO): **5/5 ✅** (sitemap+robots+JSON-LD+canonical+OG images)
  - Track H (content depth): **5/5 ✅** (5 ключевых статей расширены практическим контентом)
- Этап 9: **в работе** 🔄
  - Track I (статьи): **5/5 ✅** (observability, metrics, tracing, alerting, runbook)
  - Track J (skills): **2/2 ✅** (metrics-exporter, postmortem)
  - Track K (инженерные): 0/1 (страница /metrics)
  - Track L (поддержка): 0/4

> Объём перевода оригинала: **25/25** статей. Всего в гайде: **31 статья** (+6 RU-оригинальных). Skills: **4** (+3 RU-оригинальных). Сборка зелёная (**39 SSG-страниц** + `/feed.xml` + `/search.json` + `/robots.txt` + `/sitemap.xml`).
