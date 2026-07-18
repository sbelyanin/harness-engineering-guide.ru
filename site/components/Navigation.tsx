"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import ThemeToggle from "./ThemeToggle";

const navLinks = [
  { href: "/guide/what-is-harness", label: "Гайд" },
  { href: "/changelog", label: "Changelog" },
];

export default function Navigation() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-[var(--color-bg-primary)]/80 backdrop-blur-md border-b border-[var(--color-border)]">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between">
          <Link
            href="/"
            className="flex items-center gap-2 font-[family-name:var(--font-heading)] text-lg font-bold text-[var(--color-text-primary)] hover:text-[var(--color-accent-cyan)] transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" fill="none" className="w-7 h-7 shrink-0">
              <defs>
                <radialGradient id="navGlow" cx="50%" cy="50%" r="25%">
                  <stop offset="0%" stopColor="#00E5FF" stopOpacity={0.6}/>
                  <stop offset="50%" stopColor="#00E5FF" stopOpacity={0.15}/>
                  <stop offset="100%" stopColor="#00E5FF" stopOpacity={0}/>
                </radialGradient>
              </defs>
              <circle cx="100" cy="100" r="50" fill="url(#navGlow)"/>
              <polyline points="72,52 42,100 72,148" stroke="currentColor" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
              <polyline points="128,52 158,100 128,148" stroke="currentColor" strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
              <rect x="88" y="88" width="24" height="24" rx="3" fill="#00E5FF" transform="rotate(45 100 100)"/>
            </svg>
            <span>Harness Guide</span>
          </Link>

          {/* Desktop nav */}
          <div className="hidden sm:flex items-center gap-6">
            {navLinks.map((link) => {
              const isActive = pathname.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`text-sm transition-colors ${
                    isActive
                      ? "text-[var(--color-accent-cyan)]"
                      : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
            <a
              href="https://github.com/nexu-io/harness-engineering-guide"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              GitHub
            </a>
            <ThemeToggle />
          </div>

          {/* Mobile menu button */}
          <button
            className="sm:hidden text-[var(--color-text-muted)]"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            <svg
              className="w-6 h-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              {mobileOpen ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="sm:hidden border-t border-[var(--color-border)] bg-[var(--color-bg-primary)]">
          <div className="px-4 py-3 space-y-2">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="block text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                onClick={() => setMobileOpen(false)}
              >
                {link.label}
              </Link>
            ))}
            <a
              href="https://github.com/nexu-io/harness-engineering-guide"
              target="_blank"
              rel="noopener noreferrer"
              className="block text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
            >
              GitHub
            </a>
            <div className="flex items-center gap-3 pt-2">
              <ThemeToggle />
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
