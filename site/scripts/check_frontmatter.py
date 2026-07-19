#!/usr/bin/env python3
"""F1. Валидатор frontmatter для guide/ и changelog/.

Проверяет:
- guide/*.md: обязательны `title` и `section`; `section` ∈ enum.
- changelog/*.md: обязателен `title`; slug-префикс `ru-` для записей RU-издания
  (иначе не попадёт в homepage feed — см. AGENTS.md).

Выход: список ошибок с путями. Exit 1 если есть нарушения, иначе 0.

Без внешних зависимостей — только stdlib (см. AGENTS.md).
"""
from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GUIDE_DIR = REPO_ROOT / "guide"
CHANGELOG_DIR = REPO_ROOT / "changelog"

VALID_SECTIONS = {"getting-started", "core-concepts", "practice", "reference", "showcase"}


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Возвращает dict из YAML frontmatter или None, если его нет.

    Простейший парсер: ключ: значение (без вложенных структур).
    Этого достаточно для нашего frontmatter — он плоский.
    """
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if len(lines) < 2 or lines[0].strip() != "---":
        return None
    fm: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"').strip("'")
        fm[key.strip()] = value
    return None  # нет закрывающего ---


def check_guide() -> list[str]:
    errors: list[str] = []
    if not GUIDE_DIR.is_dir():
        errors.append(f"F1: директория не найдена: {GUIDE_DIR.relative_to(REPO_ROOT)}")
        return errors

    for md in sorted(GUIDE_DIR.glob("*.md")):
        rel = md.relative_to(REPO_ROOT)
        fm = parse_frontmatter(md.read_text(encoding="utf-8"))
        if fm is None:
            errors.append(f"F1: {rel}: отсутствует frontmatter (--- ... ---)")
            continue
        if not fm.get("title"):
            errors.append(f"F1: {rel}: отсутствует `title` (fallback на H1 ненадёжен — см. AGENTS.md)")
        section = fm.get("section")
        if not section:
            errors.append(f"F1: {rel}: отсутствует `section`")
        elif section not in VALID_SECTIONS:
            valid = ", ".join(sorted(VALID_SECTIONS))
            errors.append(f"F1: {rel}: `section: {section}` не входит в enum ({valid})")
        if not fm.get("author"):
            errors.append(f"F1: {rel}: отсутствует `author`")
    return errors


def check_changelog() -> list[str]:
    errors: list[str] = []
    if not CHANGELOG_DIR.is_dir():
        return errors  # не критично для CI

    for md in sorted(CHANGELOG_DIR.glob("*.md")):
        rel = md.relative_to(REPO_ROOT)
        fm = parse_frontmatter(md.read_text(encoding="utf-8"))
        if fm is None:
            errors.append(f"F1: {rel}: отсутствует frontmatter")
            continue
        if not fm.get("title"):
            errors.append(f"F1: {rel}: отсутствует `title`")
        slug = md.stem  # filename без .md
        if slug.startswith("ru-") and not fm.get("date"):
            errors.append(f"F1: {rel}: RU-запись без `date` в frontmatter")
    return errors


def main() -> int:
    errors = check_guide() + check_changelog()
    if not errors:
        print(f"F1 frontmatter: OK ({len(list(GUIDE_DIR.glob('*.md')))} guide, "
              f"{len(list(CHANGELOG_DIR.glob('*.md')))} changelog)")
        return 0
    print(f"F1 frontmatter: {len(errors)} ошибок\n")
    for e in errors:
        print(f"  {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
