# AGENTS.md

Русскоязычное standalone-издание [harness-engineering-guide](https://github.com/nexu-io/harness-engineering-guide). Контент живёт в корне репо, Next.js-сайт — в `site/`. Подробный план развития — в [`ROADMAP.md`](ROADMAP.md), конвенция перевода — там же.

## Критичные ловушки

- **Контент не синхронизируется автоматически.** `site/lib/content.ts:8` читает из `process.cwd()/content/`, а эта директория **генерируется** скриптом `site/scripts/sync-content.sh` из корневых `guide/` и `changelog/` и **gitignore'нута**. Правка `guide/foo.md` **не повлияет** на сайт, пока не запущен sync. В `package.json` нет prebuild-хука.
- **Next.js 16.2.3 — не та версия, что в тренировочных данных.** Перед правками кода Next.js читай `site/node_modules/next/dist/docs/01-app/`. Существующий `site/AGENTS.md` уже содержит это предупреждение — не удаляй.

## Команды разработки

Все команды — из `site/`, если не указано иное.

```bash
# Полный цикл проверки перед коммитом (порядок важен)
bash site/scripts/sync-content.sh        # 1. скопировать guide/ changelog/ → site/content/
cd site && npm install                   # 2. поставить зависимости (npm, НЕ pnpm/yarn)
npm run build                            # 3. сборка = SSG в site/out/ + проверка TypeScript

# Локальная разработка
cd site && npm run dev                   # http://localhost:3000, требует site/content/ — сначала sync
```

- **Тестов и lint-скриптов нет.** `next build` запускает TypeScript-проверку — это единственный статический верификатор. Если нужен typecheck без полной сборки — `npx tsc --noEmit`.
- **Менеджер пакетов — только npm.** `package-lock.json` закоммичен; `pnpm-lock.yaml`/`yarn.lock` занесены в `.gitignore` умышленно. Если случайно создал — удали.
- **Деплой:** push в `main` триггерит `.github/workflows/deploy-site.yml` → Cloudflare Pages. Локальный артефакт сборки — `site/out/` (статический экспорт через `output: "export"` + `trailingSlash: true`).

## Структура и регистрация контента

- **Источники истины для гайда** (порядок приоритета при конфликте):
  1. `guide/<slug>.md` — markdown-статья с frontmatter
  2. `site/lib/guide-data.ts` — каноничный порядок разделов, sidebar-навигация, slug→title
  3. `README.md` — оглавление для GitHub
- **Новая статья = 3 обязательных шага**, иначе соберётся, но не появится в навигации:
  1. Создать `guide/<slug>.md` с frontmatter (`title`, `section`, `author`)
  2. Зарегистрировать в `guide-data.ts` → `guideSections` (slug + короткий title для sidebar)
  3. Добавить строку в таблицу `README.md`
- **Frontmatter-конвенция** (`section` — один из: `getting-started`, `core-concepts`, `practice`, `reference`, `showcase`):
  ```yaml
  ---
  title: "Заголовок статьи"
  section: practice
  author: Nexu
  ---
  ```
- **Title fallback** в `content.ts:132`: `frontmatter.title || первый "# H1" в body || slug`. Prefer explicit `title:` — body H1 всё равно рендерится отдельно.
- **Skills** — в `skills/<name>/` с `SKILL.md` (frontmatter: `name`, `description`) и опциональными `scripts/`. Перечисляются в `skills/README.md`.

## Конвенция перевода и стиля

- **Технические термины остаются на английском** (Harness, Agent, Context, Tool, Sandbox, Guardrails, Skill, Sub-Agent, Loop, Memory, Session). Переводится только связующая проза. Эталоны: `guide/russian-llm-harness.md`, `guide/on-prem-harness.md`.
- **Standalone-русский**: один язык сайта. Нет маршрутов `/ru`/`/zh`, нет `LangSwitcher`, нет `isZh`, нет `zh-guide/`. Не добавляй языковые префиксы.
- **Код, JSON, ASCII-диаграммы не переводятся** — сохраняются дословно. Переводятся только комментарии внутри по необходимости.
- **Связанные руководства** см. в [`CONTRIBUTING.md`](CONTRIBUTING.md) и `ROADMAP.md` (раздел «Конвенция перевода»).

## Особенности кодовой базы сайта

- **App Router, React 19, Tailwind v4** (`@tailwindcss/postcss`). Path-алис `@/*` → `site/*`.
- **SSG-only**: каждая страница должна быть статически генерируемой. Не используй server-actions, dynamic API без `generateStaticParams`, middleware с запросами.
- **Контент рендерится через `remark`/`remark-html`** в `content.ts` (НЕ через MDX). Инжекции ID для заголовков и `target="_blank"` для внешних ссылок делаются regex'ами в `processMarkdown` — учти при изменении.
- **Навигация** захардкожена в `site/components/Navigation.tsx` (`navLinks`). Новая страница верхнего уровня требует ручного добавления.

## Существующие инструкции

- `site/AGENTS.md` — предупреждение о нестандартной версии Next.js (применимо только при работе в `site/`).
- `site/CLAUDE.md` — просто `@AGENTS.md`, дублирует для Claude Code.
