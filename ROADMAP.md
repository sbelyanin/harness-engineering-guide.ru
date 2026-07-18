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

Цель: рабочий скелет проекта + эталонная статья + проверка пайплайна.

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

## Этап 7 — Расширение (бессрочно)

Проект растёт независимо от оригинала:
- [ ] Новые статьи под русскоязычную аудиторию
- [ ] Локальные примеры/кейсы
- [ ] Отдельный `changelog` для RU-издания
- [ ] Сообщество: чат, контрибьюшены

---

## Прогресс

- Этап 1: **завершён** ✅
- Этап 2: **завершён** ✅ (7 статей)
- Этап 3: **завершён** ✅ (14 статей Practice)
- Этап 4: **завершён** ✅ (Reference + Showcase)
- Этап 5: **завершён** ✅ (changelog, skills, README, .github)
- Этап 6: **завершён** ✅ (финальная проверка)
- Этап 7: **в работе** 🔄 (независимое развитие русскоязычного издания)

> Объём оригинала: **25 статей**. Переведено: **25/25** статей. Сборка зелёная (30 SSG-страниц).
