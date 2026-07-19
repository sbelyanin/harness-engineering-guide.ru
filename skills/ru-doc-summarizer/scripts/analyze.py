#!/usr/bin/env python3
"""
Chunker для длинных русскоязычных документов.

Утилита для map-reduce саммаризации: режет документ на chunk'и по границам
заголовков, чтобы каждое окно контекста сохраняло логическую целостность, а не
случайные N строк. Полезно, когда документ длиннее контекстного окна модели.

Использование:
    python analyze.py split --input doc.md --max-tokens 4000 --out-dir chunks/
    python analyze.py outline --input doc.md
    python analyze.py refs --input doc.md

Скрипт intentionally dependency-light: требует только tiktoken при возможности
(иначе оценивает токены как len(text) // 3).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENC.encode(text))

except Exception:
    def count_tokens(text: str) -> int:
        # грубая эвристика: русский ~3 знака на токен
        return max(1, len(text) // 3)


# Паттерны заголовков markdown и нумерованных разделов русскоязычных документов.
# Нумерованный раздел требует минимум одного подраздела (1.1, 1.2.3) — иначе
# это markdown ordered-list item, а не заголовок.
HEADING_RE = re.compile(
    r"^(?P<hash>#{1,6})\s+(?P<title>.+?)\s*$"
    r"|"
    r"^(?P<num>\d+\.\d+(?:\.\d+){0,3})[.\s]+(?P<ntitle>[^\n]+)$",
    re.MULTILINE,
)

# Эвристики для извлечения ссылок (см. SKILL.md шаг 3)
REF_PATTERNS = [
    ("section", r"согласно\s+п\.?\s*\d[\.\d]*"),
    ("compliance", r"в\s+соответствии\s+с\s+(?!настоящ)"),
    ("directive", r"распоряжени\w+\s*№?\s*[\w\-/]+"),
    ("order", r"приказ\w*\s+(?:от|№)"),
    ("gost", r"ГОСТ\s*Р?\s*[\d\-\.]+"),
    ("rfc", r"\bRFC\s*\d+"),
]


@dataclass
class Section:
    level: int
    title: str
    number: str | None
    start: int
    end: int
    tokens: int

    @property
    def id(self) -> str:
        prefix = self.number or ""
        slug = re.sub(r"[^\w\s-]", "", self.title.lower())
        slug = re.sub(r"\s+", "-", slug).strip("-")
        return f"{prefix} {slug}".strip() if prefix else slug


def parse_outline(text: str) -> list[Section]:
    """Возвращает иерархию разделов с границами в исходном тексте."""
    matches: list[tuple[int, int, int, str, str | None]] = []
    for m in HEADING_RE.finditer(text):
        if m.group("hash"):
            level = len(m.group("hash"))
            title = m.group("title").strip()
            number = None
        else:
            level = m.group("num").count(".") + 1
            title = m.group("ntitle").strip()
            number = m.group("num")
        matches.append((m.start(), m.end(), level, title, number))

    if not matches:
        return [
            Section(
                level=1,
                title="(без заголовков)",
                number=None,
                start=0,
                end=len(text),
                tokens=count_tokens(text),
            )
        ]

    sections: list[Section] = []
    for i, (start, _end, level, title, number) in enumerate(matches):
        body_end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        body = text[start:body_end]
        sections.append(
            Section(
                level=level,
                title=title,
                number=number,
                start=start,
                end=body_end,
                tokens=count_tokens(body),
            )
        )
    return sections


def chunk_by_sections(
    text: str, sections: list[Section], max_tokens: int
) -> list[dict]:
    """
    Группирует мелкие разделы, пока не достигнет max_tokens.
    Крупные разделы (>max_tokens) режутся по абзацам с запасом перекрытия.
    """
    chunks: list[dict] = []
    buffer: list[Section] = []
    buffer_tokens = 0

    def flush():
        nonlocal buffer, buffer_tokens
        if not buffer:
            return
        body = "".join(text[s.start : s.end] for s in buffer)
        chunks.append(
            {
                "title": buffer[0].title,
                "number": buffer[0].number,
                "tokens": buffer_tokens,
                "sections": [asdict(s) for s in buffer],
                "preview": body[:200].replace("\n", " "),
            }
        )
        buffer = []
        buffer_tokens = 0

    for s in sections:
        if s.tokens > max_tokens:
            flush()
            body = text[s.start : s.end]
            para_split = re.split(r"\n\s*\n", body)
            sub_buf: list[str] = []
            sub_tokens = 0
            for para in para_split:
                pt = count_tokens(para)
                if sub_tokens + pt > max_tokens and sub_buf:
                    chunks.append(
                        {
                            "title": s.title,
                            "number": s.number,
                            "tokens": sub_tokens,
                            "sections": [asdict(s)],
                            "preview": "".join(sub_buf)[:200].replace("\n", " "),
                        }
                    )
                    sub_buf = []
                    sub_tokens = 0
                sub_buf.append(para)
                sub_tokens += pt
            if sub_buf:
                chunks.append(
                    {
                        "title": s.title,
                        "number": s.number,
                        "tokens": sub_tokens,
                        "sections": [asdict(s)],
                        "preview": "".join(sub_buf)[:200].replace("\n", " "),
                    }
                )
            continue

        if buffer_tokens + s.tokens > max_tokens:
            flush()
        buffer.append(s)
        buffer_tokens += s.tokens

    flush()
    return chunks


def extract_refs(text: str) -> list[dict]:
    refs: list[dict] = []
    for kind, pattern in REF_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            # номер строки для source span
            line = text.count("\n", 0, m.start()) + 1
            refs.append(
                {
                    "kind": kind,
                    "match": m.group(0),
                    "line": line,
                }
            )
    return refs


def cmd_outline(args: argparse.Namespace) -> int:
    text = Path(args.input).read_text(encoding="utf-8")
    sections = parse_outline(text)
    total = sum(s.tokens for s in sections)
    print(f"# Outline: {args.input}")
    print(f"# Всего разделов: {len(sections)}, ~{total} токенов\n")
    for s in sections:
        indent = "  " * (s.level - 1)
        prefix = f"[{s.number}] " if s.number else ""
        print(f"{indent}{prefix}{s.title}  (~{s.tokens} ток, строки {s.start}-{s.end})")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    text = Path(args.input).read_text(encoding="utf-8")
    sections = parse_outline(text)
    chunks = chunk_by_sections(text, sections, args.max_tokens)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for i, c in enumerate(chunks, 1):
        chunk_path = out_dir / f"chunk-{i:03d}.md"
        body = "".join(text[s["start"] : s["end"]] for s in c["sections"])
        chunk_path.write_text(body, encoding="utf-8")
        manifest.append({**c, "file": chunk_path.name})

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"✓ Создано {len(chunks)} chunk'ей в {out_dir}/")
    print(f"  Средний размер: {sum(c['tokens'] for c in manifest)//max(1,len(manifest))} токенов")
    return 0


def cmd_refs(args: argparse.Namespace) -> int:
    text = Path(args.input).read_text(encoding="utf-8")
    refs = extract_refs(text)
    if not refs:
        print("Ссылок не найдено.")
        return 0
    print(f"# Найдено ссылок: {len(refs)}\n")
    by_kind: dict[str, list[dict]] = {}
    for r in refs:
        by_kind.setdefault(r["kind"], []).append(r)
    for kind, items in by_kind.items():
        print(f"## {kind} ({len(items)})")
        for r in items[:20]:
            print(f"  строка {r['line']:>5}: {r['match']}")
        if len(items) > 20:
            print(f"  ...и ещё {len(items) - 20}")
        print()
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_outline = sub.add_parser("outline", help="Карта заголовков документа")
    p_outline.add_argument("--input", required=True)
    p_outline.set_defaults(func=cmd_outline)

    p_split = sub.add_parser("split", help="Разрезать документ на chunk'и")
    p_split.add_argument("--input", required=True)
    p_split.add_argument("--max-tokens", type=int, default=4000)
    p_split.add_argument("--out-dir", default="chunks")
    p_split.set_defaults(func=cmd_split)

    p_refs = sub.add_parser("refs", help="Найти ссылки на внешние документы")
    p_refs.add_argument("--input", required=True)
    p_refs.set_defaults(func=cmd_refs)

    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
