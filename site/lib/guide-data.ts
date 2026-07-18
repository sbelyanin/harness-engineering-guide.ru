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
