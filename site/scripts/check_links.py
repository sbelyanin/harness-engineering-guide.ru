#!/usr/bin/env python3
"""F3. Линкер внутренних ссылок.

Скандирует Markdown-файлы в `guide/`, `README.md`, `ROADMAP.md`, `CONTRIBUTING.md`
и проверяет, что внутренние ссылки резолвятся в реально существующие файлы/якоря.

Что считается «внутренней ссылкой»:
- `[text](path)` где path не начинается с `http://`, `https://`, `#`, `mailto:`.
- Относительные пути от репо-рут или от самого файла.

Что НЕ проверяется:
- Ссылки внутри code-блоков (``` ... ```) и inline-code (`...`).
- Внешние URLs (http/https/mailto).
- Anchor-only ссылки `#section` (пока не реализовано — было бы хрупко).

Exit 1 при битых ссылках, иначе 0. Без внешних зависимостей.
"""
from __future__ import annotations
import re
import sys
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Файлы, которые сканируются (относительно REPO_ROOT).
SCAN_TARGETS_ROOT = ["README.md", "ROADMAP.md", "CONTRIBUTING.md", "STYLE.md", "AGENTS.md"]
SCAN_DIRS = ["guide", "changelog", "skills"]


def iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    for name in SCAN_TARGETS_ROOT:
        p = REPO_ROOT / name
        if p.is_file():
            files.append(p)
    for d in SCAN_DIRS:
        dd = REPO_ROOT / d
        if dd.is_dir():
            files.extend(sorted(dd.rglob("*.md")))
    return files


def strip_code_blocks(text: str) -> str:
    """Удаляет fenced code-блоки (```), сохраняя прозу.

    Использует построчный state-machine: открывает fence на строке из ```,
    закрывает на следующей строке из >=3 backticks. Корректно для CommonMark
    (включая nested fences с разной длиной).
    """
    out: list[str] = []
    in_fence = False
    fence_len = 0
    for line in text.splitlines():
        stripped = line.lstrip()
        m = re.match(r"^(`{3,})", stripped)
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
            out.append(line)
    return "\n".join(out)


def strip_inline_code(text: str) -> str:
    """Удаляет inline-code `...` (но не fence ```...```).
    Простая замена: вырезаем короткие `...` фрагменты в одной строке.
    """
    return re.sub(r"`[^`\n]{1,200}`", "", text)


LINK_RE = re.compile(r"\[(?:[^\]\\]|\\.)+\]\(([^)]+)\)")


def extract_internal_links(text: str) -> list[str]:
    """Возвращает list URL'ов из [text](url), фильтруя внешние."""
    raw = strip_code_blocks(text)
    raw = strip_inline_code(raw)
    urls: list[str] = []
    for m in LINK_RE.finditer(raw):
        url = m.group(1).strip()
        # отбрасываем title в [text](url "title")
        url = url.split()[0] if " " in url and not url.startswith(" ") else url
        if not url:
            continue
        if url.startswith(("http://", "https://", "mailto:", "#", "tel:")):
            continue
        urls.append(url)
    return urls


def resolve_link(link: str, source: Path) -> Path | None:
    """Превращает link в абсолютный путь, относительно source.

    Поддерживаемые формы:
    - `/guide/<slug>` или `/changelog/<slug>` → URL-путь к SSG-странице;
      валидируется как `guide/<slug>.md` (slug без расширения).
    - `/path/to/file` → абсолютный путь от REPO_ROOT.
    - `relative/path` → относительно директории source.
    - `./path`, `../path` → относительно source.
    """
    decoded = urllib.parse.unquote(link)
    path_part = decoded.split("#", 1)[0].split("?")[0]
    if not path_part:
        return None

    if path_part.startswith("/"):
        # URL-путь SSG-страницы или файл от репо-рут
        segments = path_part.strip("/").split("/")
        if len(segments) == 2 and segments[0] in ("guide", "changelog"):
            # /guide/foo → guide/foo.md (если .md нет — это сломанная ссылка)
            cand = REPO_ROOT / segments[0] / f"{segments[1]}.md"
            if cand.exists():
                return cand
            # может быть index-страница раздела (пока нет)
            return cand  # вернём — валидатор скажет «нет файла»
        if len(segments) == 1 and segments[0] in ("", "community"):
            return REPO_ROOT  # всегда существует (homepage/community-page)
        return (REPO_ROOT / path_part.lstrip("/")).resolve()

    return (source.parent / path_part).resolve()


def main() -> int:
    files = iter_markdown_files()
    broken: list[tuple[Path, str, str]] = []
    checked = 0

    for src in files:
        try:
            text = src.read_text(encoding="utf-8")
        except OSError as e:
            broken.append((src, "(read error)", str(e)))
            continue
        for link in extract_internal_links(text):
            target = resolve_link(link, src)
            if target is None:
                continue
            checked += 1
            if not target.exists():
                rel = src.relative_to(REPO_ROOT) if src.is_absolute() else src
                broken.append((rel, link, str(target.relative_to(REPO_ROOT) if target.is_absolute() else target)))

    if not broken:
        print(f"F3 links: OK (проверено {checked} внутренних ссылок в {len(files)} файлах)")
        return 0
    print(f"F3 links: {len(broken)} битых ссылок\n")
    for src, link, target in broken:
        print(f"  {src}: [{link}] → нет {target}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
