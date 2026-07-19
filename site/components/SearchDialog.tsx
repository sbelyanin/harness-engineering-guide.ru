"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";

interface SearchDocument {
  slug: string;
  title: string;
  section: string;
  description: string;
  text: string;
}

interface SearchResult {
  slug: string;
  title: string;
  section: string;
  snippet: string;
  score: number;
}

const SECTION_LABELS: Record<string, string> = {
  "getting-started": "Введение",
  "core-concepts": "Базовые концепции",
  practice: "Практика",
  reference: "Справочник",
  showcase: "Кейсы",
};

const SNIPPET_RADIUS = 60;

function buildSnippet(text: string, query: string): string {
  const idx = text.indexOf(query);
  if (idx === -1) {
    // Совпадение в title/description — возвращаем начало body
    return text.slice(0, SNIPPET_RADIUS * 2).trim() + (text.length > SNIPPET_RADIUS * 2 ? "…" : "");
  }
  const start = Math.max(0, idx - SNIPPET_RADIUS);
  const end = Math.min(text.length, idx + query.length + SNIPPET_RADIUS);
  return (start > 0 ? "…" : "") + text.slice(start, end).trim() + (end < text.length ? "…" : "");
}

function search(docs: SearchDocument[], query: string): SearchResult[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const terms = q.split(/\s+/).filter(Boolean);

  const results: SearchResult[] = [];
  for (const doc of docs) {
    let score = 0;
    const titleLower = doc.title.toLowerCase();
    const descLower = doc.description.toLowerCase();

    for (const term of terms) {
      if (titleLower.includes(term)) score += 10;
      if (descLower.includes(term)) score += 5;
      if (doc.text.includes(term)) score += 1;
    }

    if (score > 0) {
      // Бонус за покрытие всех термов (а не только некоторых)
      const allTermsInText = terms.every((t) => doc.text.includes(t) || titleLower.includes(t) || descLower.includes(t));
      if (allTermsInText && terms.length > 1) score *= 2;

      results.push({
        slug: doc.slug,
        title: doc.title,
        section: doc.section,
        snippet: buildSnippet(doc.text, terms[0]),
        score,
      });
    }
  }

  return results.sort((a, b) => b.score - a.score).slice(0, 8);
}

interface SearchDialogProps {
  open: boolean;
  onClose: () => void;
}

export default function SearchDialog({ open, onClose }: SearchDialogProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [docs, setDocs] = useState<SearchDocument[] | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Lazy-load search index при первом открытии
  useEffect(() => {
    if (open && !docs) {
      fetch("/search.json")
        .then((r) => r.json())
        .then((data: SearchDocument[]) => setDocs(data))
        .catch(() => setDocs([]));
    }
  }, [open, docs]);

  // Фокус на input при открытии
  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(t);
    } else {
      setQuery("");
      setResults([]);
      setActiveIndex(0);
    }
  }, [open]);

  // Поиск с debounce
  useEffect(() => {
    if (!docs) {
      setResults([]);
      return;
    }
    const t = setTimeout(() => {
      setResults(search(docs, query));
      setActiveIndex(0);
    }, 80);
    return () => clearTimeout(t);
  }, [query, docs]);

  // Закрытие по Escape, навигация по стрелкам
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && results[activeIndex]) {
        const slug = results[activeIndex].slug;
        onClose();
        window.location.href = `/guide/${slug}`;
      }
    },
    [onClose, results, activeIndex]
  );

  useEffect(() => {
    if (open) {
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [open, handleKeyDown]);

  // Прокрутка активного результата в зону видимости
  useEffect(() => {
    const container = resultsRef.current;
    if (!container) return;
    const active = container.querySelector(`[data-idx="${activeIndex}"]`);
    active?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[10vh] px-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-2xl bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--color-border)]">
          <svg
            className="w-5 h-5 text-[var(--color-text-muted)] shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск по гайду…"
            className="flex-1 bg-transparent border-0 outline-none text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]"
            autoComplete="off"
            spellCheck={false}
          />
          <button
            onClick={onClose}
            className="text-xs text-[var(--color-text-muted)] px-2 py-1 rounded border border-[var(--color-border)] hover:bg-[var(--color-bg-secondary)]"
          >
            Esc
          </button>
        </div>

        {/* Results */}
        <div ref={resultsRef} className="max-h-[60vh] overflow-y-auto">
          {docs === null ? (
            <div className="px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
              Загрузка индекса…
            </div>
          ) : query && results.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
              Ничего не найдено по запросу «{query}»
            </div>
          ) : results.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
              {docs.length} статей в индексе. Начните вводить запрос.
            </div>
          ) : (
            <ul className="py-2">
              {results.map((r, idx) => (
                <li key={r.slug}>
                  <Link
                    href={`/guide/${r.slug}`}
                    onClick={onClose}
                    data-idx={idx}
                    className={`block px-4 py-3 transition-colors ${
                      idx === activeIndex
                        ? "bg-[var(--color-accent-cyan-dim)]"
                        : "hover:bg-[var(--color-bg-secondary)]"
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-3 mb-1">
                      <span className="font-medium text-[var(--color-text-primary)]">
                        {r.title}
                      </span>
                      {r.section && SECTION_LABELS[r.section] && (
                        <span className="text-xs text-[var(--color-text-muted)] shrink-0">
                          {SECTION_LABELS[r.section]}
                        </span>
                      )}
                    </div>
                    {r.snippet && (
                      <p className="text-sm text-[var(--color-text-muted)] line-clamp-2">
                        {r.snippet}
                      </p>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-[var(--color-border)] flex items-center justify-between text-xs text-[var(--color-text-muted)]">
          <span className="flex items-center gap-2">
            <kbd className="px-1.5 py-0.5 rounded border border-[var(--color-border)]">↑↓</kbd>
            навигация
          </span>
          <span className="flex items-center gap-2">
            <kbd className="px-1.5 py-0.5 rounded border border-[var(--color-border)]">↵</kbd>
            открыть
          </span>
        </div>
      </div>
    </div>
  );
}
