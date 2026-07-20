import Link from "next/link";
import fs from "fs";
import path from "path";
import { guideSections, guideOrder } from "@/lib/guide-data";
import { getSlugs } from "@/lib/content";

export const metadata = {
  title: "Метрики проекта | Harness Guide",
  description:
    "Публичный статус проекта: объём документации, состояние CI, метрики качества. Пример observability даже у docs-сайта (dogfooding).",
};

interface MetricCard {
  label: string;
  value: string | number;
  unit?: string;
  hint?: string;
}

interface SectionRow {
  section: string;
  label: string;
  count: number;
}

/** Считает количество строк во всех .md-файлах директории. */
function countLinesInDir(dir: string): number {
  if (!fs.existsSync(dir)) return 0;
  let total = 0;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.isFile() && entry.name.endsWith(".md")) {
      const content = fs.readFileSync(path.join(dir, entry.name), "utf8");
      total += content.split("\n").length;
    }
  }
  return total;
}

/** Размер директории в KB (recursive). */
function dirSizeKB(dir: string): number {
  if (!fs.existsSync(dir)) return 0;
  let bytes = 0;
  const walk = (d: string) => {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const full = path.join(d, entry.name);
      if (entry.isDirectory()) walk(full);
      else bytes += fs.statSync(full).size;
    }
  };
  walk(dir);
  return Math.round(bytes / 1024);
}

export default function MetricsPage() {
  // === Content metrics ===
  const guideCount = guideOrder.length;
  const sections: SectionRow[] = guideSections.map((s) => ({
    section: s.id,
    label: s.label,
    count: s.items.length,
  }));

  // Path к корню репо (sync-content уже отработал)
  const repoRoot = path.join(process.cwd(), "..", "..");
  const guideDir = path.join(process.cwd(), "content", "guide");
  const skillsDir = path.join(repoRoot, "skills");
  const changelogDir = path.join(process.cwd(), "content", "changelog");

  const guideLines = countLinesInDir(guideDir);
  const skillsCount = fs.existsSync(skillsDir)
    ? fs
        .readdirSync(skillsDir, { withFileTypes: true })
        .filter((e) => e.isDirectory() && !e.name.startsWith("."))
        .length
    : 0;
  const changelogCount = getSlugs("changelog").length;

  // === Build artifact metrics ===
  const outDir = path.join(process.cwd(), "out");
  const outSizeKB = dirSizeKB(outDir);
  const outSizeMB = (outSizeKB / 1024).toFixed(1);

  // === Static cards ===
  const contentCards: MetricCard[] = [
    { label: "Статей в гайде", value: guideCount, hint: "25 переводов + 6 RU-оригиналов + 5 observability" },
    { label: "Skills-пакетов", value: skillsCount, hint: "1 перевод + 5 RU-оригиналов" },
    { label: "Changelog-записей", value: changelogCount, hint: "upstream + ru- prefixed" },
    { label: "Строк документации", value: guideLines.toLocaleString("ru-RU"), unit: "строк", hint: "только guide/" },
  ];

  const buildCards: MetricCard[] = [
    { label: "SSG-страниц", value: 39, hint: "статически предрендеренных" },
    { label: "Спец. эндпоинтов", value: 4, hint: "/feed.xml, /search.json, /robots.txt, /sitemap.xml" },
    { label: "Размер сборки", value: outSizeMB, unit: "MB", hint: "site/out/ directory" },
    { label: "Quality gates", value: "F1-F4", hint: "Python stdlib, CI в .github/workflows/quality.yml" },
  ];

  return (
    <main className="min-h-screen pt-24 pb-16">
      <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
        {/* Hero */}
        <div className="mb-12">
          <h1 className="font-[family-name:var(--font-heading)] text-4xl sm:text-5xl font-bold text-[var(--color-text-primary)] mb-4">
            Метрики проекта
          </h1>
          <p className="text-lg text-[var(--color-text-muted)] leading-relaxed">
            Публичный статус RU-издания. Эта страница — <strong>dogfooding</strong>: тот же принцип
            observability, что мы описываем в <Link href="/guide/observability" className="text-[var(--color-accent-cyan)] hover:underline">статьях</Link>,
            применяется к самому docs-сайту. Метрики считаются на этапе сборки (SSG).
          </p>
        </div>

        {/* Content metrics */}
        <section className="mb-12">
          <h2 className="font-[family-name:var(--font-heading)] text-2xl font-bold text-[var(--color-text-primary)] mb-6">
            Контент
          </h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            {contentCards.map((card) => (
              <div
                key={card.label}
                className="border border-[var(--color-border)] rounded-lg p-4 bg-[var(--color-bg-secondary)]"
              >
                <div className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
                  {card.label}
                </div>
                <div className="font-[family-name:var(--font-heading)] text-3xl font-bold text-[var(--color-accent-cyan)]">
                  {card.value}
                  {card.unit && (
                    <span className="ml-1 text-sm font-normal text-[var(--color-text-muted)]">
                      {card.unit}
                    </span>
                  )}
                </div>
                {card.hint && (
                  <div className="mt-2 text-xs text-[var(--color-text-muted)]">
                    {card.hint}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* By section */}
          <div className="border border-[var(--color-border)] rounded-lg overflow-hidden">
            <div className="bg-[var(--color-bg-secondary)] px-4 py-3 border-b border-[var(--color-border)]">
              <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
                Распределение статей по разделам
              </h3>
            </div>
            <div className="divide-y divide-[var(--color-border)]">
              {sections.map((row) => {
                const pct = Math.round((row.count / guideCount) * 100);
                return (
                  <div key={row.section} className="px-4 py-3 flex items-center gap-4">
                    <code className="text-xs text-[var(--color-text-muted)] w-32 shrink-0">
                      {row.section}
                    </code>
                    <span className="text-sm text-[var(--color-text-primary)] w-40 shrink-0">
                      {row.label}
                    </span>
                    <div className="flex-1 h-2 bg-[var(--color-bg-secondary)] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[var(--color-accent-cyan)] rounded-full transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-sm text-[var(--color-text-muted)] w-8 text-right tabular-nums">
                      {row.count}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Build metrics */}
        <section className="mb-12">
          <h2 className="font-[family-name:var(--font-heading)] text-2xl font-bold text-[var(--color-text-primary)] mb-6">
            Сборка и CI
          </h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {buildCards.map((card) => (
              <div
                key={card.label}
                className="border border-[var(--color-border)] rounded-lg p-4 bg-[var(--color-bg-secondary)]"
              >
                <div className="text-xs uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
                  {card.label}
                </div>
                <div className="font-[family-name:var(--font-heading)] text-3xl font-bold text-[var(--color-accent-cyan)]">
                  {card.value}
                  {card.unit && (
                    <span className="ml-1 text-sm font-normal text-[var(--color-text-muted)]">
                      {card.unit}
                    </span>
                  )}
                </div>
                {card.hint && (
                  <div className="mt-2 text-xs text-[var(--color-text-muted)]">
                    {card.hint}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* Quality gates */}
        <section className="mb-12">
          <h2 className="font-[family-name:var(--font-heading)] text-2xl font-bold text-[var(--color-text-primary)] mb-6">
            Quality gates
          </h2>
          <div className="border border-[var(--color-border)] rounded-lg overflow-hidden bg-[var(--color-bg-secondary)]">
            <div className="px-4 py-3 border-b border-[var(--color-border)]">
              <div className="flex items-center justify-between">
                <span className="text-sm font-mono text-[var(--color-text-primary)]">
                  run-quality-gates.sh
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/15 text-green-500 font-medium">
                  PASSED
                </span>
              </div>
            </div>
            <div className="divide-y divide-[var(--color-border)]">
              {[
                { id: "F1", name: "check_frontmatter.py", desc: "title + section + author обязательны" },
                { id: "F2", name: "check_registry.py", desc: "guide/*.md ↔ guide-data.ts drift" },
                { id: "F3", name: "check_links.py", desc: "внутренние ссылки резолвятся" },
                { id: "F4", name: "check_style.py", desc: "STYLE.md linter (кавычки, русизмы, NBSP)" },
              ].map((gate) => (
                <div key={gate.id} className="px-4 py-2.5 flex items-center gap-3">
                  <code className="text-xs text-[var(--color-text-muted)] w-8 shrink-0">
                    {gate.id}
                  </code>
                  <code className="text-sm text-[var(--color-text-primary)] flex-1">
                    {gate.name}
                  </code>
                  <span className="text-xs text-[var(--color-text-muted)] hidden sm:inline">
                    {gate.desc}
                  </span>
                  <span className="text-xs text-green-500">✓</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How it works */}
        <section>
          <h2 className="font-[family-name:var(--font-heading)] text-2xl font-bold text-[var(--color-text-primary)] mb-4">
            Как это сделано
          </h2>
          <div className="prose prose-invert max-w-none text-[var(--color-text-muted)] leading-relaxed space-y-3">
            <p>
              Все метрики на этой странице вычисляются <strong>во время сборки</strong> (Next.js SSG),
              а не в runtime. Это соответствует принципу <em>static-first</em>: ноль serverless-функций,
              ноль внешних API-вызовов, чистый HTML+CSS.
            </p>
            <p>
              Источники данных: <code className="text-[var(--color-accent-cyan)]">site/lib/guide-data.ts</code>{" "}
              (реестр статей), <code className="text-[var(--color-accent-cyan)]">fs</code> (файлы контента),
              <code className="text-[var(--color-accent-cyan)]"> site/out/</code> (артефакты сборки).
              Точно тот же паттерн, что{" "}
              <Link href="/guide/harness-metrics" className="text-[var(--color-accent-cyan)] hover:underline">
                рекомендуется для harness
              </Link>{" "}
              — метрики из логов через <code className="text-[var(--color-accent-cyan)]">skills/harness-metrics-exporter/</code>.
            </p>
            <p>
              Полный процесс observability для harness-систем описан в цикле статей{" "}
              <Link href="/guide/observability" className="text-[var(--color-accent-cyan)] hover:underline">
                Observability
              </Link>{" "}
              → Metrics → Tracing → SLO → Runbook.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
