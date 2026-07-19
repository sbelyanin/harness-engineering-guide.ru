#!/usr/bin/env python3
"""F4. Linter конвенций STYLE.md.

Проверяет правила, которые легко нарушить случайно и которые автоматически
нарушают стиль сайта:

1. **ASCII `"..."` в prose** — должны быть «ёлочки».
   (В code-блоках и YAML frontmatter ASCII quotes разрешены.)
2. **Русские транслитерации EN терминов** — фиксируется канон в STYLE.md § 1.1:
   фреймворк→framework, пайплайн→pipeline, фича→feature, фидбек→feedback,
   дашборд→dashboard, бэкенд→backend, хэш→хеш.
3. **NBSP в source markdown** — typographRussian() в content.ts расставляет
   NBSP автоматически на уровне HTML. В .md исходниках их быть не должно
   (иначе дубликаты или странный diff).

Exit 1 при нарушениях, иначе 0. Без внешних зависимостей.
"""
from __future__ import annotations
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SCAN_DIRS = ["guide", "changelog"]
SCAN_FILES_ROOT = ["README.md", "ROADMAP.md", "CONTRIBUTING.md"]

# STYLE.md § 1.1 — термины, которые должны остаться на английском.
# Форма: русская транслитерация → правильный английский вариант.
FORBIDDEN_RUSSIANISMS = {
    "фреймворк": "framework",
    "фреймворке": "framework",
    "фреймворком": "framework",
    "фреймворка": "framework",
    "пайплайн": "pipeline",
    "пайплайна": "pipeline",
    "пайплайном": "pipeline",
    "фича": "feature",
    "фичи": "feature",
    "фичу": "feature",
    "фидбек": "feedback",
    "дашборд": "dashboard",
    "бэкенд": "backend",
    "бэкенда": "backend",
    "хэш": "хеш",  # орфография, не англицизм
}

# NBSP-подобные символы (U+00A0, U+2007, U+202F, U+2060)
NBSP_CHARS = {"\u00a0", "\u2007", "\u202f", "\u2060"}


def strip_frontmatter(text: str) -> tuple[str, int]:
    """Удаляет YAML frontmatter (--- ... ---) — там ASCII quotes разрешены.

    Возвращает (body_without_frontmatter, frontmatter_line_count).
    """
    if not text.startswith("---"):
        return text, 0
    lines = text.splitlines()
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return ("\n".join(lines[i + 1:]), i + 1)
    return text, 0


def strip_inline_code(line: str) -> str:
    """Удаляет inline-code `...` из строки (но не fence ```...```).
    Заменяет на пробел, чтобы сохранить позиции символов.
    """
    def repl(m):
        return " " * len(m.group(0))
    return re.sub(r"`[^`\n]{1,400}`", repl, line)


def strip_html_tags(line: str) -> str:
    """Удаляет HTML-теги `<...>` и их атрибуты — там ASCII quotes валидны.
    Заменяет на пробелы для сохранения позиций.
    """
    def repl(m):
        return " " * len(m.group(0))
    return re.sub(r"<[^>\n]{1,400}>", repl, line)


def iter_prose_lines(text: str, line_offset: int = 0):
    """Y'ит (file_line_no, line) по строкам вне fenced code-блоков.

    State-machine: открывает fence на ```-строке, закрывает на следующей
    ```-строке с тем же числом backticks (CommonMark-совместимо).
    """
    in_fence = False
    fence_len = 0
    for i, line in enumerate(text.splitlines(), start=1):
        m = re.match(r"^(`{3,})", line.lstrip())
        if m:
            this_len = len(m.group(1))
            if not in_fence:
                in_fence = True
                fence_len = this_len
                continue
            elif this_len >= fence_len:
                in_fence = False
                fence_len = 0
                continue
        if not in_fence:
            yield (i + line_offset, line)


ASCII_QUOTE_RE = re.compile(r'"[^"\n]{1,200}"')


def find_ascii_quotes(line: str) -> list[tuple[int, str]]:
    """Возвращает [(start_col, matched)] для ASCII "..." в строке."""
    return [(m.start(), m.group()) for m in ASCII_QUOTE_RE.finditer(line)]


def find_russianisms(line: str) -> list[tuple[int, str, str]]:
    """Возвращает [(col, bad_word, correct_word)] для запрещённых русизмов."""
    out: list[tuple[int, str, str]] = []
    lower = line.lower()
    for bad, good in FORBIDDEN_RUSSIANISMS.items():
        for m in re.finditer(re.escape(bad), lower):
            col = m.start()
            # убедимся, что это отдельное слово (не часть другого)
            before = line[col - 1] if col > 0 else " "
            after = line[m.end()] if m.end() < len(line) else " "
            if before.isalnum() or after.isalnum():
                continue
            out.append((col, line[m.start():m.end()], good))
    return out


def find_nbsp(line: str) -> list[tuple[int, str]]:
    """Возвращает [(col, char_name)] для NBSP-подобных символов."""
    out: list[tuple[int, str]] = []
    for i, ch in enumerate(line):
        if ch in NBSP_CHARS:
            out.append((i, unicodedata.name(ch, "U+%04X" % ord(ch))))
    return out


def iter_scan_files() -> list[Path]:
    files: list[Path] = []
    for name in SCAN_FILES_ROOT:
        p = REPO_ROOT / name
        if p.is_file():
            files.append(p)
    for d in SCAN_DIRS:
        dd = REPO_ROOT / d
        if dd.is_dir():
            files.extend(sorted(dd.glob("*.md")))
    return files


def main() -> int:
    violations: list[str] = []

    for src in iter_scan_files():
        text = src.read_text(encoding="utf-8")
        body, offset = strip_frontmatter(text)
        rel = src.relative_to(REPO_ROOT)
        for line_no, line in iter_prose_lines(body, offset):
            # Убираем inline-code и HTML-теги — там ASCII quotes разрешены
            clean = strip_html_tags(strip_inline_code(line))
            # ASCII "..."
            for col, matched in find_ascii_quotes(clean):
                violations.append(
                    f"{rel}:{line_no}:{col}: ASCII quotes «{matched}» — "
                    f"используй «ёлочки» (STYLE.md § 2.1)"
                )
            # Запрещённые русизмы
            for col, bad, good in find_russianisms(clean):
                violations.append(
                    f"{rel}:{line_no}:{col}: русизм «{bad}» — "
                    f"используй «{good}» (STYLE.md § 1.1)"
                )
            # NBSP
            for col, name in find_nbsp(line):
                violations.append(
                    f"{rel}:{line_no}:{col}: NBSP-символ ({name}) в source — "
                    f"typographRussian() применит автоматически (AGENTS.md)"
                )

    if not violations:
        total = len(iter_scan_files())
        print(f"F4 style: OK (проверено {total} файлов)")
        return 0
    print(f"F4 style: {len(violations)} нарушений\n")
    for v in violations:
        print(f"  {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
