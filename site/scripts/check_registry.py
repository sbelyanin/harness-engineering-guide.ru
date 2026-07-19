#!/usr/bin/env python3
"""F2. Детектор registry drift: guide-data.ts ↔ guide/*.md.

Согласно AGENTS.md, новая статья требует 3 шага (создать файл, зарегистрировать
в guide-data.ts, добавить в README). Шаг 2 легко забыть — статья соберётся, но
не появится в навигации. Этот скрипт ловит расхождения.

Проверяет:
- Каждый `guide/*.md` зарегистрирован в `guideSections` (`site/lib/guide-data.ts`).
- Каждый slug в `guideSections` имеет соответствующий файл `guide/<slug>.md`.
- Заголовок в `guideSections` соответствует `frontmatter.title` (мягкое предупреждение).

Exit 1 при drift'е, иначе 0. Без внешних зависимостей.
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GUIDE_DIR = REPO_ROOT / "guide"
GUIDE_DATA = REPO_ROOT / "site" / "lib" / "guide-data.ts"


def parse_frontmatter_title(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            return None
        if line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return None


def extract_registry_entries(tsx_source: str) -> dict[str, str]:
    """Парсит `slug: "...", title: "..."` из guide-data.ts.

    Возвращает {slug: title}. Не использует TS-парсер — регекс достаточен
    для нашей плоской структуры.
    """
    entries: dict[str, str] = {}
    pattern = re.compile(r'slug:\s*"([^"]+)"\s*,\s*title:\s*"([^"]+)"')
    for m in pattern.finditer(tsx_source):
        entries[m.group(1)] = m.group(2)
    return entries


def main() -> int:
    if not GUIDE_DATA.is_file():
        print(f"F2: файл не найден: {GUIDE_DATA.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 2
    if not GUIDE_DIR.is_dir():
        print(f"F2: директория не найдена: {GUIDE_DIR.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 2

    tsx = GUIDE_DATA.read_text(encoding="utf-8")
    registry = extract_registry_entries(tsx)

    files_on_disk = {md.stem: md for md in GUIDE_DIR.glob("*.md")}

    in_fs_not_registry = sorted(set(files_on_disk) - set(registry))
    in_registry_not_fs = sorted(set(registry) - set(files_on_disk))

    errors: list[str] = []
    for slug in in_fs_not_registry:
        errors.append(
            f"F2 DRIFT: guide/{slug}.md существует, но не зарегистрирован в "
            f"site/lib/guide-data.ts → не попадёт в sidebar навигации."
        )
    for slug in in_registry_not_fs:
        errors.append(
            f"F2 DRIFT: slug «{slug}» в guide-data.ts, но файл guide/{slug}.md "
            f"отсутствует → broken link в навигации."
        )

    title_mismatches: list[str] = []
    for slug, reg_title in sorted(registry.items()):
        md = files_on_disk.get(slug)
        if not md:
            continue
        fm_title = parse_frontmatter_title(md.read_text(encoding="utf-8"))
        if fm_title and fm_title != reg_title:
            title_mismatches.append(
                f"F2 INFO: {slug}.md: title расходится — frontmatter «{fm_title}» vs "
                f"guide-data.ts «{reg_title}» (не ошибка, но проверь)"
            )

    if errors:
        print(f"F2 registry drift: {len(errors)} проблем\n")
        for e in errors:
            print(f"  {e}")
        if title_mismatches:
            print("\nДополнительно (информационно):")
            for m in title_mismatches:
                print(f"  {m}")
        return 1

    print(f"F2 registry drift: OK ({len(registry)} статей синхронизировано)")
    if title_mismatches:
        print(f"\nИнформационно ({len(title_mismatches)} расхождений title):")
        for m in title_mismatches:
            print(f"  {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
