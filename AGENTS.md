# AGENTS.md

Русскоязычное standalone-издание [harness-engineering-guide](https://github.com/nexu-io/harness-engineering-guide). Контент — в корне репо (`guide/`, `changelog/`, `skills/`), Next.js-сайт — в `site/`. Канон стиля — [`STYLE.md`](STYLE.md), план развития — [`ROADMAP.md`](ROADMAP.md).

## Критичные ловушки

- **Контент не синхронизируется автоматически.** `site/lib/content.ts:8` читает из `process.cwd()/content/`, а эта директория **генерируется** скриптом `site/scripts/sync-content.sh` из корневых `guide/` и `changelog/` и **gitignore'нута**. Правка `guide/foo.md` **не повлияет** на сайт, пока не запущен sync. В `package.json` **нет prebuild-хука** — sync надо запускать вручную перед каждым `next build`.
- **Next.js 16.2.3 — не та версия, что в тренировочных данных.** Перед правками кода Next.js читай `site/node_modules/next/dist/docs/01-app/`. Существующий `site/AGENTS.md` содержит это предупреждение — не удаляй.
- **Mojibake-сканер в `content.ts`.** HTML post-processing в `processMarkdown` (`content.ts:116`) вызывает `typographRussian()`, который автоматически расставляет NBSP после русских предлогов/союзов и между числом+единицей. Code-блоки (`<code>`, `<pre>`) пропускаются через state-machine split. **Не вставляй NBSP в markdown-исходники вручную** — они применятся при рендере.
- **RU-changelog фильтр.** Homepage feed «Что нового в RU-издании» (`site/app/page.tsx:11`) фильтрует записи по slug-префиксу `ru-`. Запись без префикса (например `changelog/2026-07-22.md`) в ленту **не попадёт**. Конвенция: `changelog/ru-YYYY-MM-DD.md`.

## Команды разработки

Все команды — из `site/`, если не указано иное.

```bash
# Полный цикл проверки перед коммитом (порядок важен)
bash site/scripts/run-quality-gates.sh     # 0. статические проверки контента (F1-F4)
bash site/scripts/sync-content.sh          # 1. скопировать guide/ changelog/ → site/content/
cd site && npm install                     # 2. поставить зависимости (npm, НЕ pnpm/yarn)
npm run build                              # 3. сборка = SSG в site/out/ + проверка TypeScript

# Локальная разработка
cd site && npm run dev                     # http://localhost:3000, требует site/content/ — сначала sync

# Typecheck без полной сборки
cd site && npx tsc --noEmit
```

- **Quality gates (F1-F4)** запускаются перед каждым commit'ом и в CI (`.github/workflows/quality.yml`). Если меняешь контент в `guide/`/`changelog/` или `site/lib/guide-data.ts` — обязательно прогони локально. Скрипты в `site/scripts/check_*.py`, runner — `run-quality-gates.sh`. Без внешних зависимостей (Python stdlib).
  - **F1** `check_frontmatter.py` — `title` + `section` + `author` обязательны в `guide/*.md`.
  - **F2** `check_registry.py` — детект drift'а между `guide/*.md` и `guide-data.ts` (новый файл без регистрации → не попадёт в sidebar).
  - **F3** `check_links.py` — внутренние ссылки (`/guide/<slug>`, относительные пути) резолвятся.
  - **F4** `check_style.py` — STYLE.md-конвенции: ASCII `"..."` в prose, русизмы (`фреймворк`/`пайплайн`/...), NBSP в исходниках.

- **Тестов и lint-скриптов нет.** `next build` запускает TypeScript-проверку — единственный статический верификатор кода сайта. Контент-проверки — quality gates F1-F4 (см. выше).
- **Менеджер пакетов — только npm.** `package-lock.json` закоммичен; `pnpm-lock.yaml`/`yarn.lock` занесены в `.gitignore` умышленно. Если случайно создал — удали.
- **Деплой:** push в `main` триггерит `.github/workflows/deploy-site.yml` → Cloudflare Pages. Локальный артефакт — `site/out/` (статический экспорт через `output: "export"` + `trailingSlash: true`).

## Регистрация контента

- **Новая статья = 3 обязательных шага**, иначе соберётся, но не появится в навигации:
  1. Создать `guide/<slug>.md` с frontmatter (`title`, `section`, `author`)
  2. Зарегистрировать в `site/lib/guide-data.ts` → `guideSections` (slug + короткий title для sidebar)
  3. Добавить строку в таблицу `README.md`
- **`section`** — один из: `getting-started`, `core-concepts`, `practice`, `reference`, `showcase`.
- **Title fallback** в `content.ts:169`: `frontmatter.title || первый "# H1" в body || slug`. Prefer explicit `title:` — body H1 всё равно рендерится отдельно.
- **Новый skill** — в `skills/<name>/` с `SKILL.md` (frontmatter: `name`, `description`) и опциональными `scripts/`. Python-скрипты — **только stdlib**, без внешних зависимостей (иначе сломается deploy). Зарегистрируй в таблице `skills/README.md`.
- **Новая страница верхнего уровня** на сайте — требует ручного добавления в `site/components/Navigation.tsx` (`navLinks`).

## Стиль и конвенции

Полный канон — в [`STYLE.md`](STYLE.md). Краткая выжимка того, что легко нарушить случайно:

- **Технические термины — на английском:** Harness, Agent, Context, Tool, Sandbox, Guardrails, Skill, Sub-Agent, Loop, Memory, Session, Pipeline, Framework, Feature, Feedback, Dashboard, Backend, Deploy. Падежи через апостроф: `framework'ом`, `pipeline'ами`.
- **Допустимые русизмы** (давно в техническом языке, не заменять): `баг`, `ветка` (git), `лог`, `токен`, `кэш`.
- **Standalone-русский**: один язык сайта. Нет маршрутов `/ru`/`/zh`, нет `LangSwitcher`, нет `isZh`. Не добавляй языковые префиксы.
- **Кавычки**: только `«ёлочки»` в прозе. ASCII `"..."` — только в code-блоках и YAML frontmatter.
- **Тире**: `—` (em-dash) в прозе, `–` (en-dash) для диапазонов чисел (`1.2–1.5×`, `20–30%`), `-` (hyphen) для сложных слов (`CI-пайплайн`).
- **Код, JSON, ASCII-диаграммы не переводятся** — сохраняются дословно. Переводятся только комментарии внутри по необходимости.
- **Эталоны перевода:** `guide/russian-llm-harness.md`, `guide/on-prem-harness.md`. Подробнее — в [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Особенности кодовой базы сайта

- **App Router, React 19, Tailwind v4** (`@tailwindcss/postcss`). Path-алис `@/*` → `site/*`.
- **SSG-only**: каждая страница должна быть статически генерируемой. Не используй server-actions, dynamic API без `generateStaticParams`, middleware с запросами.
- **Контент рендерится через `remark`/`remark-html`** в `content.ts` (НЕ через MDX). В `processMarkdown` три post-processing шага: ID для заголовков → `target="_blank"` для внешних ссылок → `typographRussian` (NBSP). При изменении — учти порядок.

## Существующие инструкции

- `site/AGENTS.md` — предупреждение о нестандартной версии Next.js (применимо только при работе в `site/`).
- `site/CLAUDE.md` — `@AGENTS.md`, дублирует для Claude Code.
