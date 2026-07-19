---
title: "Initializer + Coding Agent — двухфазный паттерн Harness"
section: practice
author: Nexu
date: "2026-04-19"
description: "Почему одиночный agent-loop с compaction не может построить многодневный проект и как разбиение harness на фазу Initializer и повторяющуюся фазу Coding это чинит."
tags: [harness, long-running-agents, context-engineering, patterns]
---

# Initializer + Coding Agent — двухфазный паттерн Harness

Если вы когда-нибудь давали fronttier-coding-модели промпт вроде *«собери мне клон Claude.ai»* и уходили до вечера, вы знаете, чем это кончается: репо с рабочей формой логина, половиной списка сообщений, `TODO: hook up streaming` посреди файла и очень уверенным commit-сообщением. У модели кончился context.

Первый порыв — винить модель. Почти всегда виноват harness.

Этот пост — про конкретный паттерн, который чинит класс таких провалов: **разбейте своего долгоиграющего агента на две фазы — Initializer, который запускается один раз, и Coding Agent, который запускается много раз, каждая session делает ровно одну feature на чистом листе.**

Он основан на [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) с референсом в [autonomous-coding quickstart](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding). Я хочу разобрать, *почему* это работает, а не только как выглядит.

---

## Главный инсайт: compaction недостаточен

Стандартный ответ на «context window конечен» — compaction. Саммаризуйте старое, оставьте новое, крутите вечно.

Compaction ок для двухчасового рефакторинга. Для двухдневной сборки он разваливается.

Натравите Opus 4.5 на Agent SDK на высокоуровневый промпт вроде «собери клон Claude.ai» и смотрите:

- Session 1 пишет много кода и упирается в лимит context с наполовину готовыми feature'ами.
- Session 2 читает компактнутое саммари — лоссивую, нарративную версию произошедшего — и должна реконструировать намерения из него.
- Session 3 читает compaction от compaction. Информация деградирует геометрически.

К session 4 модель играет в испорченный телефон с прошлой собой. Она не знает, какие feature готовы, какие наполовину, а какие нагаллюцинированы в саммари.

**Compaction — это in-context memory. Долгоиграющим агентам нужна out-of-context memory** — файлы, структурированное состояние, git-история. То, что агент перечитывает каждую session, а не тащит через саммаризацию.

Это тезис. Всё остальное — механика.

---

## Два failure-мода, в которые вы упрётесь

Прежде чем перейдём к паттерну, уточним, что именно идёт не так без него. Доминируют два failure-мода.

### (A) One-shot-тенденция

Модель пытается сделать всё за одну session. Получив большой промпт, пишет большое решение. context заполняется. Она продолжает толкаться. session заканчивается с наполовину реализованными feature'ами, `// TODO` посреди функций, тест-сьютом, который не запускается, и без чистого коммита, к которому можно вернуться. Модель не знает, что она сломана — у неё кончилось место раньше, чем она смогла проверить.

### (B) Преждевременная победа

Коварнее. Session 2 читает progress-заметки Session 1: «реализованы login, messaging, streaming». Модель смотрит на код, видит что-то, *похожее* на login + messaging + streaming, и объявляет проект готовым. Она его не запускала. Не тестировала flow. Она доверилась нарративу.

Преждевременная победа — двойник one-shot. One-shot падает, потому что модель пытается сделать слишком много; преждевременная победа — потому что следующая модель доверяет оптимизму предыдущей. Любой harness для долгоиграющей работы должен решить **обе** сразу. Поэтому наивное «просто крутить с compaction» не катит — compaction усиливает нарратив предыдущей session, что в точности ошибочно, когда тот нарратив излишне оптимистичен.

---

## Двухфазный Harness

Фикс структурный. Один агент не делает всё. У вас две роли с разными обязанностями и разным lifetime.

```
 ┌──────────────────────────────────────────────────────────────┐
 │                        HARNESS DRIVER                         │
 │                     (ваш Python-скрипт)                       │
 └──────────────────────────────────────────────────────────────┘
                   │                              │
                   │ запускается 1 раз            │ запускается N раз
                   ▼                              ▼
 ┌──────────────────────────┐     ┌──────────────────────────────┐
 │    INITIALIZER AGENT     │     │        CODING AGENT          │
 │                          │     │                              │
 │ • читает spec / brief    │     │ • pwd + read git log         │
 │ • пишет init.sh          │     │ • читает claude-progress.txt │
 │ • пишет feature_list.json│     │ • читает feature_list.json   │
 │ • пишет progress-файл    │     │ • берёт приоритетнейший unit │
 │ • git init + 1-й коммит  │     │ • запускает init.sh (dev)    │
 │                          │     │ • реализует ОДНУ фичу        │
 │                          │     │ • e2e-тест через браузер     │
 │                          │     │ • переключает passes: true   │
 │                          │     │ • коммит + обновляет progress│
 └──────────────────────────┘     └──────────────────────────────┘
              │                                  ▲
              │                                  │
              └───── репо в чистом состоянии ────┘
                     (разделяется на диске)
```

Initializer запускается **один раз**. Его работа — превратить размытый человеческий бриф в конкретный машиночитаемый план плюс runnable-каркас.

Coding-агент запускается **много раз**, каждый выз — свежий процесс без памяти о предыдущем. Память он получает, читая файлы, которые предыдущие session'ы записали на диск.

Два агента, две цели, одна разделяемая файловая система.

---

## Агент-Initializer

Initializer — единственная фаза, которая думает о проекте целиком. После неё никто больше не имеет глобального представления — каждая coding-session работает локально.

Четыре артефакта, не больше:

1. **`init.sh`** — один скрипт, поднимающий проект с холодного чекаута: поставить зависимости, прогнать миграции, стартовать dev-сервер в фоне, напечатать URL. Каждая coding-session запускает его первым. Если `init.sh` сломан — больше ничего не важно.
2. **`feature_list.json`** — декомпозированный backlog. Формат — в следующем разделе.
3. **`claude-progress.txt`** — короткие прозовые заметки, где проект и что дальше. Обновляются в конце каждой session.
4. **Начальный git-коммит** — каркас, скрипты, список feature, progress-файл — всё на `HEAD`. Отсюда каждая session заканчивается коммитом. `git log` — источник правды о том, что реально вышло.

Initializer не реализует feature. Не подбирает цвета. Он накрывает на стол.

---

## Дизайн списка feature: почему JSON бьёт Markdown

«Это же просто todo-list, почему не Markdown-чеклист?»

Потому что когда вы даёте Claude Markdown-файл, он трактует его как прозу. Проза редактируема. Модель — с лучшими намерениями — перепишет ваши приоритеты, переформулирует описания, объединит две feature, потому что «чище», разобьёт одну на пять, потому что «уточняет». Markdown todo-списки для агентов — зыбучие пески.

JSON другой. Модели обучены трактовать JSON как структурированные данные — то, из чего читают и пишут конкретные поля, а не произвольно переписывают. В сочетании с явным правилом, что перезаписывать можно только одно поле, JSON становится почти пуленепробиваемым внешним состоянием.

Разумная схема:

```json
{
  "project": "claude-ai-clone",
  "created_at": "2026-04-19T10:00:00Z",
  "features": [
    {
      "id": "auth-01",
      "title": "Email + password sign up",
      "description": "User can create account with email + password. Passwords hashed with bcrypt. Email uniqueness enforced.",
      "priority": 1,
      "depends_on": [],
      "acceptance": [
        "POST /api/signup returns 201 with session cookie",
        "duplicate email returns 409",
        "password stored as bcrypt hash, not plaintext"
      ],
      "passes": false
    },
    {
      "id": "auth-02",
      "title": "Email + password sign in",
      "description": "User can log in with credentials from auth-01.",
      "priority": 2,
      "depends_on": ["auth-01"],
      "acceptance": [
        "POST /api/signin with valid creds returns 200 + cookie",
        "wrong password returns 401",
        "signed-in user can load /app"
      ],
      "passes": false
    },
    {
      "id": "chat-01",
      "title": "Minimal chat page with message list",
      "description": "Authenticated user sees a chat page with past messages rendered from the DB.",
      "priority": 3,
      "depends_on": ["auth-02"],
      "acceptance": [
        "GET /chat renders <ul> of messages",
        "unauthenticated GET /chat redirects to /signin"
      ],
      "passes": false
    }
  ]
}
```

Дисциплина закодирована в system-промпте coding-агента:

> You may only modify the `passes` field. It is unacceptable to remove or edit tests, acceptance criteria, descriptions, or the structure of this file. If you believe a feature is wrong, stop and report — do not silently rewrite it.

Эта формулировка не хеджирование — она несущая. «Unacceptable» читается моделью как жёсткое правило. На практике этого хватает, чтобы файл оставался стабильным десятки session.

`passes: false` — другая критичная деталь. Это единственный рычаг агента. Когда session реализует feature, проходит e2e-тесты и коммитит чисто, она переключает boolean в `true`. Одно поле — не проза, не ощущения — так будущие session'ы знают, что реально готово.

---

## Coding-агент: startup-ритуал, а не свободный полёт

Каждый раз, просыпаясь, coding-агент прогоняет один и тот же пятишаговый ритуал, прежде чем трогать код. Не опционально.

```
1. pwd                         → подтверждаем, что мы в проекте
2. git log --oneline -20       → что вышло, свежее первым
   cat claude-progress.txt     → нарративные заметки прошлой session
3. cat feature_list.json       → что готово, что дальше, что заблокировано
4. bash init.sh                → install, migrate, старт dev-сервера
5. открыть приложение в браузере → проверить, что работа прошлой session жива
```

Только после шага 5 агент берёт feature и начинает писать код.

Назовём это **context bootstrap** — out-of-context-эквивалент compaction. Вместо наследования саммари агент реконструирует рабочий context из файлов на диске. Те же канонические источники, тот же порядок, каждую session.

Пара вещей, которые стоит зафиксировать:

- **Git log раньше progress-заметок.** Git — источник правды; progress-заметки оптимистичны. Если они расходятся, побеждает git.
- **`init.sh` обязателен.** Если dev-сервер не стартует, не важно, что заявляла предыдущая session.
- **E2E-проверка перед выбором новой feature.** Это и убивает преждевременную победу. Вы не доверяете «готово» предыдущей session — вы открываете браузер.

На шаге 3 агент берёт *единственную приоритетнейшую feature с `passes: false` и всеми удовлетворёнными зависимостями*. Не две. Не «кластер». Одну. Затем останавливается, когда она зелёная и закоммичена.

Одна-feature-за-session убивает оба failure-мода сразу: one-shot — потому что контракт искусственно ограничивает scope; преждевременную победу — потому что «готово» не самозаявлено, а это e2e-тест, зелёный на чётко очерченном unit.

---

## End-to-end-тестирование — слой доверия

Unit-тесты необходимы, но недостаточны. Их написал coding-агент — они не могут быть единственным, кто их проверяет. Если модель неправильно поняла spec, unit-тесты будут неправильны той же формы, что реализация, и пройдут так, что это ничего не значит.

E2E — где вы получаете независимый сигнал. Поднять реальное приложение, погонять как пользователь, посмотреть, что будет.

На практике это браузерная автоматизация. [Puppeteer MCP](https://github.com/modelcontextprotocol/servers) работает хорошо — агент может навигировать, заполнять формы, кликать и проверять DOM.

Проверка для `auth-01`:

```
→ navigate to http://localhost:3000/signup
→ fill #email with "test+{{timestamp}}@example.com"
→ fill #password with "correct-horse-battery-staple"
→ click button[type=submit]
→ assert url === "/app"
→ assert response cookie "session" is set
→ navigate to /signup again with same email
→ fill + submit
→ assert error text contains "already exists"
```

Три вещи: (1) гоняется против реального сервера, который поднял `init.sh`, не мок; (2) проверяет наблюдаемое поведение — URL, DOM, куки — не внутренние функции; (3) достаточно дёшево, чтобы гонять каждую session, поэтому bootstrap-проверка «пережила ли работа прошлой session?» — это же e2e-прогон по уже зелёным feature'ам.

Это и делает `passes: true` осмысленным.

---

## Коммиты чистого состояния: git + progress-файл вместе

В конце каждой coding-session последовательно происходят две вещи:

1. `git commit -m "feat(auth-01): email+password signup"` — код ложится.
2. `claude-progress.txt` получает короткое дополнение — что вышло, что тонко, куда следующей session смотреть первым.

Они делают разную работу. Git — слой **правды**: append-only, с timestamp'ами, дифф не оспорим. `claude-progress.txt` — слой **подсказок**: заметки следующему агенту вроде «email-шаблоны лежат в `/lib/email/`, я обезьяньим патчем поправил SMTP-клиент для тестов, берегись race в `/api/signin`, я обошёл retry».

Оба читаются в начале каждой session. По отдельности недостаточны. Git без подсказок лаконичен, из него тяжело реконструировать намерение. Подсказки без git дрейфуют. Вместе они — out-of-context memory, заменяющая compaction.

Оба должны оставлять session в *чистом* состоянии — никаких незакоммиченных изменений, наполовину готовых файлов, сломанного dev-сервера. Если feature не готова к лимиту context, **session откатывается к последнему чистому коммиту и сообщает «не готово»**, а не коммитит сломанную работу. Так git остаётся заслуживающим доверия.

---

## Где этот паттерн подходит (а где нет)

Будьте честны о форме вашего проекта, прежде чем тянуться к нему.

**Хорошие кандидаты:** веб-приложения (функционально декомпозируемые, e2e-тестируемые), CLI (каждая подкоманда — естественный unit), внутренние инструменты / dashboard'ы / админки, data-pipeline'ы с дискретными стадиями.

**Плохие кандидаты:** single-алгоритмные исследования вроде «спроектировать механизм внимания получше» (не разложить в `passes: true/false`), сильно связные кодовые базы, где затрагивание одной функции тянет изменения по всему коду, всё, чья ценность — в *связях* между компонентами: корректность компилятора — в глобальных инвариантах, а не «добавить лексер» + «добавить парсер».

Правило: если вы можете записать acceptance как «пользователь (или shell) делает X и наблюдает Y», паттерн работает. Иначе выбирайте другой harness.

---

## Эскиз реализации

Сам harness-драйвер маленький. Большая часть работы — в двух system-промптах.

```python
# harness.py — псевдокод, обработку ошибок опускаем для ясности
from pathlib import Path
import json, subprocess, time
from claude_sdk import run_agent

PROJECT = Path("./project")

def initialize(brief: str) -> None:
    """Run once. Turns a brief into a runnable scaffold."""
    run_agent(
        system_prompt=INITIALIZER_PROMPT,
        user_prompt=brief,
        workdir=PROJECT,
        allowed_tools=["write_file", "run_shell", "git"],
        # от initializer'а ожидается:
        #   init.sh, feature_list.json, claude-progress.txt, первый git-коммит
    )
    assert (PROJECT / "feature_list.json").exists()
    assert (PROJECT / "init.sh").exists()

def next_feature() -> dict | None:
    features = json.loads((PROJECT / "feature_list.json").read_text())["features"]
    features.sort(key=lambda f: f["priority"])
    for f in features:
        if f["passes"]:
            continue
        if all(done(dep) for dep in f["depends_on"]):
            return f
    return None  # всё готово

def done(feature_id: str) -> bool:
    features = json.loads((PROJECT / "feature_list.json").read_text())["features"]
    return any(f["id"] == feature_id and f["passes"] for f in features)

def code_one_feature() -> bool:
    feat = next_feature()
    if feat is None:
        return False
    run_agent(
        system_prompt=CODING_PROMPT,         # включает startup-ритуал
        user_prompt=f"Implement feature {feat['id']}: {feat['title']}",
        workdir=PROJECT,
        allowed_tools=["read_file", "write_file", "run_shell", "git", "puppeteer"],
    )
    # ожидается, что агент оставит чистый коммит + обновлённый progress-файл
    return True

if __name__ == "__main__":
    if not (PROJECT / "feature_list.json").exists():
        initialize(open("brief.md").read())
    while code_one_feature():
        time.sleep(1)  # свежий процесс каждую итерацию — состояния не переносится
    print("all features passed.")
```

Две вещи, которые стоит усвоить: **каждый вызов `run_agent` — абсолютно новый процесс** — без разделяемой памяти, без разделяемого context window, память — это файловая система. И **драйвер намеренно глупый** — он не выбирает feature, не валидирует работу, не интерпретирует результаты. Весь интеллект — в промптах и артефактах.

---

## Заключительная мысль

Этот паттерн работает не потому, что initializer или coding-агент умные. Он работает, потому что **на вопрос «что я знаю?» отвечают файлы на диске, а не содержимое context window.**

Каждый раз, перемещая состояние из in-context в out-of-context, вы получаете долговечность и не теряете ничего важного. Двухфазный harness — opinionated-способ такого перемещения, применённый к конкретной задаче сборки ПО через много session.

Если ваш долгоиграющий агент постоянно «забывает», фикс почти никогда не в большем context window. Он — в большем количестве файлов.

---

## Что почитать

- [scheduling-and-automation.md](./scheduling-and-automation.md) — как будить coding-агента по расписанию без человеческого присмотра
- [long-running-harness.md](./long-running-harness.md) — более широкое семейство паттернов, куда это входит
- [memory-and-context.md](./memory-and-context.md) — глубже про out-of-context memory, файловые раскладки и bootstrap-ритуалы
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — Anthropic Engineering, исходный материал
- [autonomous-coding quickstart](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding) — рабочая референс-реализация двухфазного паттерна
