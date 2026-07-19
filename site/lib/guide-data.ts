// Структура гайда — единый заголовок на русском (standalone-издание)
export interface GuideSection {
  id: string;
  label: string;
  items: { slug: string; title: string }[];
}

export const guideSections: GuideSection[] = [
  {
    id: "getting-started",
    label: "Введение",
    items: [
      { slug: "what-is-harness", title: "Что такое Harness?" },
      { slug: "your-first-harness", title: "Ваш первый Harness" },
      { slug: "harness-vs-framework", title: "Harness vs. Framework" },
    ],
  },
  {
    id: "core-concepts",
    label: "Базовые концепции",
    items: [
      { slug: "agentic-loop", title: "Agentic Loop" },
      { slug: "tool-system", title: "Tool System" },
      { slug: "memory-and-context", title: "Memory & Context" },
      { slug: "guardrails", title: "Guardrails" },
    ],
  },
  {
    id: "practice",
    label: "Практика",
    items: [
      { slug: "context-engineering", title: "Context Engineering" },
      { slug: "sandbox", title: "Sandbox" },
      { slug: "skill-system", title: "Skill System" },
      { slug: "sub-agent", title: "Sub-Agent" },
      { slug: "error-handling", title: "Обработка ошибок" },
      { slug: "multi-agent-orchestration", title: "Multi-Agent Orchestration" },
      { slug: "scheduling-and-automation", title: "Scheduling и автоматизация" },
      { slug: "long-running-harness", title: "Дизайн Long-Running Harness" },
      { slug: "managed-agents-architecture", title: "Архитектура Managed Agents" },
      { slug: "eval-infrastructure", title: "Шумы в Eval-инфраструктуре" },
      { slug: "classifier-permissions", title: "Permissions на основе классификатора" },
      { slug: "eval-awareness", title: "Eval Awareness" },
      { slug: "agent-teams", title: "Agent Teams" },
      { slug: "initializer-coding-pattern", title: "Паттерн Initializer + Coding Agent" },
      { slug: "russian-llm-harness", title: "Russian LLM в Harness" },
      { slug: "on-prem-harness", title: "On-Prem Harness: air-gapped" },
      { slug: "yandexgpt-and-gigachat", title: "YandexGPT и GigaChat" },
      { slug: "open-source-llm-stack", title: "Open-Source LLM-стек" },
      { slug: "cyrillic-tokenization", title: "Cyrillic Tokenization" },
      { slug: "compliance-152fz", title: "Compliance: 152-ФЗ" },
    ],
  },
  {
    id: "reference",
    label: "Справочник",
    items: [
      { slug: "comparison", title: "Сравнение реализаций" },
      { slug: "glossary", title: "Глоссарий" },
    ],
  },
  {
    id: "showcase",
    label: "Кейсы",
    items: [
      { slug: "nexu-windows-packaging", title: "Релиз нашего Windows-клиента" },
      { slug: "ghost-account-hunting", title: "Охота на ghost-аккаунты" },
    ],
  },
];

// Плоский список slug'ов по порядку
export const guideOrder = guideSections.flatMap((s) => s.items.map((i) => i.slug));

// Соответствие slug → заголовок
export const guideChapters: Record<string, string> = Object.fromEntries(
  guideSections.flatMap((s) => s.items.map((i) => [i.slug, i.title]))
);

// Соответствие slug → section id
export const guideSectionOf: Record<string, string> = Object.fromEntries(
  guideSections.flatMap((s) => s.items.map((i) => [i.slug, s.id]))
);

/** Стоп-слова, исключаемые из title-токенов для relatedness. */
const STOP_WORDS = new Set([
  // русские
  "и", "а", "но", "в", "с", "к", "у", "о", "об", "на", "по", "для", "или", "что", "как",
  "не", "ни", "же", "ли", "бы", "под", "над", "при", "из", "от", "до",
  "это", "все", "всеx", "вас", "нас", "как", "так",
  // английские
  "the", "a", "an", "of", "in", "on", "at", "to", "for", "with", "by", "and", "or",
  "from", "as", "is", "are", "be", "vs",
]);

/** Возвращает токены из заголовка (lowercase, ≥4 символов, без стоп-слов). */
function titleTokens(title: string): Set<string> {
  return new Set(
    title
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s]/gu, " ")
      .split(/\s+/)
      .filter((t) => t.length >= 4 && !STOP_WORDS.has(t))
  );
}

/** Возвращает `limit` родственных статей для `slug` по эвристике:
 *  - +5 очков, если та же section;
 *  - +1 за каждый общий значимый токен заголовка.
 *  Сам `slug` и его соседи по guideOrder исключаются (они и так в prev/next). */
export function getRelatedArticles(slug: string, limit = 3): { slug: string; title: string }[] {
  const currentSection = guideSectionOf[slug];
  const currentTokens = titleTokens(guideChapters[slug] || "");
  const idx = guideOrder.indexOf(slug);
  const neighbours = new Set([guideOrder[idx - 1], guideOrder[idx + 1]].filter(Boolean) as string[]);

  return guideOrder
    .filter((s) => s !== slug && !neighbours.has(s))
    .map((s) => {
      let score = 0;
      if (guideSectionOf[s] === currentSection) score += 5;
      const tokens = titleTokens(guideChapters[s] || "");
      for (const t of tokens) {
        if (currentTokens.has(t)) score += 1;
      }
      return { slug: s, title: guideChapters[s], score };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map(({ slug: s, title }) => ({ slug: s, title }));
}
