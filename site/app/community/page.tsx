import Link from "next/link";

export const metadata = {
  title: "Сообщество | Harness Guide",
  description:
    "Как контрибьютить в русскоязычное издание Harness Engineering Guide, где задавать вопросы и обсуждать статьи.",
};

interface Channel {
  title: string;
  url: string;
  description: string;
  external: boolean;
}

const channels: Channel[] = [
  {
    title: "GitHub Issues",
    url: "https://github.com/nexu-io/harness-engineering-guide/issues/new/choose",
    description:
      "Сообщить об ошибке в переводе, предложить правку или новую тему для статьи.",
    external: true,
  },
  {
    title: "GitHub Discussions",
    url: "https://github.com/nexu-io/harness-engineering-guide/discussions",
    description:
      "Обсудить архитектуру harness, задать вопросы по статьям, предложить кейс.",
    external: true,
  },
];

interface ContributionPath {
  title: string;
  detail: string;
  links: { label: string; href: string; external?: boolean }[];
}

const paths: ContributionPath[] = [
  {
    title: "Сообщить об опечатке или неточности",
    detail:
      "Самый быстрый вклад. Откройте Issue с указанием статьи и цитатой — правка попадёт в следующий RU-changelog.",
    links: [
      {
        label: "New Issue",
        href: "https://github.com/nexu-io/harness-engineering-guide/issues/new/choose",
        external: true,
      },
    ],
  },
  {
    title: "Улучшить перевод",
    detail:
      "Если формулировка режет слух или ломает терминологию — присылайте PR. Перед правкой сверьтесь с конвенцией перевода в ROADMAP.md.",
    links: [
      { label: "CONTRIBUTING.md", href: "/CONTRIBUTING.md" },
      { label: "ROADMAP.md", href: "/ROADMAP.md" },
    ],
  },
  {
    title: "Добавить RU-оригинальную статью",
    detail:
      "Статьи под русскоязычную аудиторию, которых нет в upstream: локальные модели, on-prem, 152-ФЗ, кейсы РФ-команд. Эталон по структуре — guide/russian-llm-harness.md и guide/on-prem-harness.md.",
    links: [{ label: "Track B в ROADMAP", href: "/ROADMAP.md#--track-b--новые-ru-оригинальные-статьи" }],
  },
  {
    title: "Добавить skills-пакет",
    detail:
      "Готовый skill с SKILL.md и опциональными скриптами под русскоязычные задачи. Эталон — skills/ru-doc-summarizer/.",
    links: [{ label: "Track C в ROADMAP", href: "/ROADMAP.md#--track-c--расширение-skills-пакетов" }],
  },
];

interface Principle {
  title: string;
  detail: string;
}

const principles: Principle[] = [
  {
    title: "Технические термины остаются на английском",
    detail:
      "Harness, Agent, Context, Tool, Sandbox, Guardrails, Skill, Sub-Agent, Loop, Memory, Session — по образцу китайского издания. Переводится только связующая проза.",
  },
  {
    title: "Точность важнее дословности",
    detail:
      "Перевод должен быть технически точным, без кальки с английского синтаксиса. Если оригинал написан коряво — улучшайте, но сохраняйте смысл.",
  },
  {
    title: "Код и ASCII-диаграммы не переводятся",
    detail:
      "Структура и содержимое кодовых блоков сохраняются. Переводятся только текстовые комментарии внутри по необходимости.",
  },
  {
    title: "Маленькие PR лучше больших",
    detail:
      "Одна статья — один PR. Правки терминологии — отдельным PR с пометкой в названии. Так быстрее ревью и проще откатить.",
  },
];

export default function CommunityPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 pt-24 pb-16">
      <h1 className="font-[family-name:var(--font-heading)] text-4xl font-bold text-[var(--color-text-primary)] mb-4">
        Сообщество
      </h1>
      <p className="text-lg text-[var(--color-text-secondary)] mb-12">
        Русскоязычное издание живёт за счёт контрибьюторов. Здесь — как помочь
        проекту и где обсуждать статьи.
      </p>

      {/* Channels */}
      <section className="mb-16">
        <h2 className="font-[family-name:var(--font-heading)] text-2xl font-semibold text-[var(--color-text-primary)] mb-6">
          Каналы связи
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {channels.map((c) => (
            <a
              key={c.url}
              href={c.url}
              target={c.external ? "_blank" : undefined}
              rel={c.external ? "noopener noreferrer" : undefined}
              className="block p-6 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] hover:border-[var(--color-accent-cyan)] transition-colors"
            >
              <h3 className="text-lg font-semibold text-[var(--color-text-primary)] mb-2">
                {c.title}
              </h3>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {c.description}
              </p>
            </a>
          ))}
        </div>
      </section>

      {/* Contribution paths */}
      <section className="mb-16">
        <h2 className="font-[family-name:var(--font-heading)] text-2xl font-semibold text-[var(--color-text-primary)] mb-6">
          Как контрибьютить
        </h2>
        <div className="space-y-6">
          {paths.map((p, i) => (
            <div
              key={p.title}
              className="relative pl-10 pb-6 border-l border-[var(--color-border)] last:border-l-transparent last:pb-0"
            >
              <div className="absolute left-0 top-0 -translate-x-1/2 w-7 h-7 rounded-full bg-[var(--color-accent-cyan-dim)] border border-[var(--color-accent-cyan)] flex items-center justify-center text-xs font-mono text-[var(--color-accent-cyan)]">
                {i + 1}
              </div>
              <h3 className="text-lg font-semibold text-[var(--color-text-primary)] mb-2">
                {p.title}
              </h3>
              <p className="text-[var(--color-text-secondary)] mb-3">
                {p.detail}
              </p>
              <div className="flex flex-wrap gap-4 text-sm">
                {p.links.map((l) => (
                  <a
                    key={l.href}
                    href={l.href}
                    target={l.external ? "_blank" : undefined}
                    rel={l.external ? "noopener noreferrer" : undefined}
                    className="text-[var(--color-accent-cyan)] hover:underline"
                  >
                    {l.label} →
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Principles */}
      <section className="mb-16">
        <h2 className="font-[family-name:var(--font-heading)] text-2xl font-semibold text-[var(--color-text-primary)] mb-6">
          Принципы контрибьюта
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {principles.map((p) => (
            <div
              key={p.title}
              className="p-5 rounded-lg bg-[var(--color-bg-secondary)] border border-[var(--color-border)]"
            >
              <h3 className="font-semibold text-[var(--color-text-primary)] mb-2">
                {p.title}
              </h3>
              <p className="text-sm text-[var(--color-text-secondary)]">
                {p.detail}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="p-8 rounded-lg bg-[var(--color-accent-cyan-dim)] border border-[var(--color-accent-cyan)]/30 text-center">
        <h2 className="font-[family-name:var(--font-heading)] text-xl font-semibold text-[var(--color-text-primary)] mb-3">
          Готовы начать?
        </h2>
        <p className="text-[var(--color-text-secondary)] mb-6">
          Откройте Issue с описанием, что хотите сделать — обсудим подход до того,
          как писать код.
        </p>
        <div className="flex flex-wrap justify-center gap-4">
          <Link
            href="/ROADMAP.md"
            className="inline-flex items-center px-5 py-2.5 rounded-md bg-[var(--color-accent-cyan)] text-[var(--color-bg-primary)] font-medium hover:opacity-90 transition-opacity"
          >
            Читать ROADMAP
          </Link>
          <a
            href="https://github.com/nexu-io/harness-engineering-guide/issues/new/choose"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center px-5 py-2.5 rounded-md border border-[var(--color-border)] text-[var(--color-text-primary)] hover:border-[var(--color-accent-cyan)] transition-colors"
          >
            Открыть Issue
          </a>
        </div>
      </section>
    </div>
  );
}
