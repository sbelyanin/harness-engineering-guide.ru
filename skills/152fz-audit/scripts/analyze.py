#!/usr/bin/env python3
"""
Детектор персональных данных (ПДн) в логах AI-агента по 152-ФЗ.

Regex-based сканер для прямых идентификаторов (email, телефон, ИНН, СНИЛС,
паспорт, PAN). Не заменяет LLM-классификатор для косвенных ПДн, но даёт
быстрый first-pass без зависимости от модели.

Использование:
    python analyze.py scan --input chatlog.jsonl --format jsonl
    python analyze.py scan --input memory/ --format dir
    python analyze.py pseudonymize --input chatlog.jsonl --out clean.jsonl

Форматы:
    jsonl — по одной session на строку: {"session_id": "..., "messages": [...]}
    json  — массив сообщений: [{"role": "...", "content": "..."}]
    txt   — свободный текст (одна session)
    dir   — директория с файлами выше
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


# --- Паттерны ПДн -----------------------------------------------------------

PATTERNS: dict[str, str] = {
    "email": r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",
    "phone_ru": r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
    "phone_intl": r"\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,}[\s\-]?\d{3,}",
    # ИНН физлица (12) или юрлица (10) — с проверкой контрольной суммы в коде
    "inn_10": r"\b\d{10}\b",
    "inn_12": r"\b\d{12}\b",
    # СНИЛС: XXX-XXX-XXX YY
    "snils": r"\b\d{3}-\d{3}-\d{3}\s?\d{2}\b",
    # Паспорт РФ: серия+номер
    "passport_ru": r"\b\d{4}\s?\d{6}\b",
    # ОМС (единый полис): 16 цифр
    "oms": r"\b\d{16}\b",
    # PAN карты — 13-19 цифр с разделителями; проверяется Luhn
    "card_pan": r"\b(?:\d[ -]*?){13,19}\b",
    # Telegram @handle (только если явно идентифицирует лицо — помечаем мягко)
    "telegram_handle": r"(?<![\w@])@(?=\w{5,32}\b)[a-zA-Z][a-zA-Z0-9_]{4,31}\b",
}

COMPILED = {name: re.compile(p) for name, p in PATTERNS.items()}


# --- Категории риска --------------------------------------------------------

UZ_LEVELS = {"UZ1", "UZ2", "UZ3", "UZ4"}

# Базовая классификация по типу находки
BASE_RISK = {
    "email": "UZ2",
    "phone_ru": "UZ2",
    "phone_intl": "UZ2",
    "inn_10": "UZ2",
    "inn_12": "UZ2",
    "snils": "UZ2",
    "passport_ru": "UZ3",
    "oms": "UZ3",
    "card_pan": "UZ3",
    "telegram_handle": "UZ1",
}


@dataclass
class Finding:
    category: str
    value: str            # само совпадение
    masked: str           # для безопасного отображения
    value_hash: str       # sha256 для дедупликации субъектов
    uz_level: str
    session_id: str | None
    position: int         # смещение в тексте
    line: int             # номер строки в исходном файле
    source_file: str | None
    passes_luhn: bool | None = None  # только для card_pan


# --- Утилиты ----------------------------------------------------------------

def mask_value(category: str, value: str) -> str:
    """Возвращает маскированное представление для безопасного вывода."""
    if category == "email":
        u, d = value.split("@", 1)
        return f"{u[:1]}***@{d[:1]}***.{d.split('.')[-1]}"
    digits = re.sub(r"\D", "", value)
    if len(digits) >= 4:
        return f"{digits[:2]}***{digits[-2:]}"
    return "***"


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def luhn_check(number: str) -> bool:
    """Проверка контрольной суммы LUHN для номеров карт."""
    digits = [int(c) for c in re.sub(r"\D", "", number)]
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    reverse = digits[::-1]
    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ИНН — упрощённая проверка контрольной цифры (для 10- и 12-значных)
def inn_check(inn: str) -> bool:
    digits = [int(c) for c in inn]
    if len(digits) == 10:
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        return sum(w * d for w, d in zip(weights, digits)) % 11 % 10 == digits[-1]
    if len(digits) == 12:
        w1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        w2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        c1 = sum(w * d for w, d in zip(w1, digits[:10])) % 11 % 10
        if c1 != digits[10]:
            return False
        c2 = sum(w * d for w, d in zip(w2, digits[:11])) % 11 % 10
        return c2 == digits[11]
    return False


# --- Парсеры входа ----------------------------------------------------------

def parse_jsonl(path: Path) -> Iterable[tuple[str | None, str]]:
    with path.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            session_id = obj.get("session_id")
            messages = obj.get("messages", [])
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        c.get("text", "") if isinstance(c, dict) else str(c)
                        for c in content
                    )
                yield session_id, f"[line {line_no}] {content}"


def parse_json(path: Path) -> Iterable[tuple[str | None, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    for msg in data:
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                c.get("text", "") if isinstance(c, dict) else str(c) for c in content
            )
        yield msg.get("session_id"), content


def parse_txt(path: Path) -> Iterable[tuple[str | None, str]]:
    yield None, path.read_text(encoding="utf-8")


def iter_sessions(input_path: Path, fmt: str) -> Iterable[tuple[str | None, str, str | None]]:
    """Yields (session_id, content, source_file)."""
    parsers = {"jsonl": parse_jsonl, "json": parse_json, "txt": parse_txt}

    if fmt == "dir":
        for child in sorted(input_path.iterdir()):
            if child.is_dir():
                continue
            ext = child.suffix.lstrip(".").lower()
            child_fmt = "jsonl" if ext == "jsonl" else "json" if ext == "json" else "txt"
            for sid, content in parsers[child_fmt](child):
                yield sid, content, str(child)
    else:
        for sid, content in parsers[fmt](input_path):
            yield sid, content, str(input_path)


# --- Сканер -----------------------------------------------------------------

def scan_text(
    text: str,
    session_id: str | None = None,
    source_file: str | None = None,
) -> list[Finding]:
    findings: list[Finding] = []

    for cat, pattern in COMPILED.items():
        for m in pattern.finditer(text):
            value = m.group()

            # Спец-проверки для уменьшения false positives
            if cat == "card_pan":
                if not luhn_check(value):
                    continue
            elif cat in {"inn_10", "inn_12"}:
                if not inn_check(value):
                    continue
            elif cat == "telegram_handle":
                # Игнорируем явно-tech-хэндлы и стандартные account-type
                if value.lower() in {"@channel", "@group", "@bot"}:
                    continue

            line = text.count("\n", 0, m.start()) + 1
            findings.append(
                Finding(
                    category=cat,
                    value=value,
                    masked=mask_value(cat, value),
                    value_hash=hash_value(value),
                    uz_level=BASE_RISK.get(cat, "UZ1"),
                    session_id=session_id,
                    position=m.start(),
                    line=line,
                    source_file=source_file,
                    passes_luhn=luhn_check(value) if cat == "card_pan" else None,
                )
            )

    return findings


def pseudonymize(text: str) -> tuple[str, list[Finding]]:
    """Маскирует ПДн в тексте, возвращает (clean_text, findings)."""
    findings = scan_text(text)
    # Заменяем от длинных к коротким, чтобы не ломать смещения
    for f in sorted(findings, key=lambda x: -x.position):
        token = f"{f.category.upper()}_{f.value_hash[:8]}"
        text = text[: f.position] + token + text[f.position + len(f.value) :]
    return text, findings


# --- Отчёт ------------------------------------------------------------------

def aggregate(findings: list[Finding]) -> dict:
    by_category: dict[str, int] = {}
    by_uz: dict[str, int] = {}
    unique_subjects: set[str] = set()
    sessions_affected: set[str | None] = set()
    highest_uz = "UZ1"
    uz_order = ["UZ1", "UZ2", "UZ3", "UZ4"]

    for f in findings:
        by_category[f.category] = by_category.get(f.category, 0) + 1
        by_uz[f.uz_level] = by_uz.get(f.uz_level, 0) + 1
        unique_subjects.add(f.value_hash)
        sessions_affected.add(f.session_id)
        if uz_order.index(f.uz_level) > uz_order.index(highest_uz):
            highest_uz = f.uz_level

    return {
        "total": len(findings),
        "by_category": by_category,
        "by_uz_level": by_uz,
        "unique_subjects_est": len(unique_subjects),
        "sessions_affected": len(sessions_affected),
        "highest_uz": highest_uz,
    }


def score_log(stats: dict) -> tuple[int, str]:
    """0-16 баллов: объём × УЗ × распространение × зрелость masking (нет → 4)."""
    total = stats["total"]
    vol = 0 if total == 0 else 1 if total < 10 else 2 if total < 50 else 3 if total < 100 else 4

    uz = stats["highest_uz"]
    uz_score = {"UZ1": 1, "UZ2": 2, "UZ3": 3, "UZ4": 4}.get(uz, 1) - 1

    sess = stats["sessions_affected"]
    spread = 0 if sess <= 1 else 1 if sess < 10 else 2 if sess < 50 else 3 if sess < 100 else 4

    maturity = 4  # нет masking в pipeline → max штраф
    score = vol + uz_score + spread + maturity
    if score <= 4:
        verdict = "✅ пригоден"
    elif score <= 9:
        verdict = "⚠️ требует pseudonymization"
    else:
        verdict = "🚨 критический — удалить + расследование"
    return score, verdict


def print_report(findings: list[Finding], stats: dict, sources: list[str]) -> None:
    score, verdict = score_log(stats)
    print("# 152ФЗ-Audit Report\n")
    print("## Источник")
    for s in sources[:5]:
        print(f"- {s}")
    if len(sources) > 5:
        print(f"- ...и ещё {len(sources) - 5}")
    print(f"\n## Сводка")
    print(f"- Всего находок: {stats['total']}")
    print(f"- Уникальных субъектов (оценка): ~{stats['unique_subjects_est']}")
    print(f"- Затронуто sessions: {stats['sessions_affected']}")
    print(f"- Высший УЗ: {stats['highest_uz']}")
    print(f"- Общий балл: {score} / 16  ({verdict})")

    print(f"\n## Распределение по категориям")
    print("| Категория | Кол-во | УЗ |")
    print("|-----------|--------|-----|")
    for cat, cnt in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
        print(f"| {cat} | {cnt} | {BASE_RISK.get(cat, 'UZ1')} |")

    print(f"\n## Топ-рисковые находки (до 10)")
    risky = [f for f in findings if f.uz_level in {"UZ3", "UZ4"}][:10]
    if not risky:
        risky = sorted(findings, key=lambda x: -len(x.value))[:10]
    for i, f in enumerate(risky, 1):
        luhn = " (Luhn ✓)" if f.passes_luhn else ""
        print(f"{i}. [{f.uz_level}] {f.category}{luhn} — {f.source_file or '?'}:{f.line}")
        print(f"   masked: {f.masked}")


# --- CLI --------------------------------------------------------------------

def cmd_scan(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Не найден input: {input_path}", file=sys.stderr)
        return 2

    all_findings: list[Finding] = []
    sources: list[str] = []

    for sid, content, src in iter_sessions(input_path, args.format):
        all_findings.extend(scan_text(content, sid, src))
        if src and src not in sources:
            sources.append(src)

    stats = aggregate(all_findings)
    print_report(all_findings, stats, sources)

    if args.out:
        Path(args.out).write_text(
            json.dumps(
                {"stats": stats, "findings": [asdict(f) for f in all_findings[:1000]]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nПолный отчёт записан в {args.out}")
    return 0


def cmd_pseudonymize(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_findings = 0
    with out_path.open("w", encoding="utf-8") as out_fh:
        for sid, content, src in iter_sessions(input_path, args.format):
            clean, found = pseudonymize(content)
            total_findings += len(found)
            if args.format == "jsonl":
                out_fh.write(
                    json.dumps({"session_id": sid, "content": clean}, ensure_ascii=False)
                    + "\n"
                )
            else:
                out_fh.write(clean + "\n---\n")

    print(f"✓ Маскировано {total_findings} находок, вывод в {out_path}")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Сканировать лог и выдать report")
    p_scan.add_argument("--input", required=True)
    p_scan.add_argument("--format", choices=["jsonl", "json", "txt", "dir"], default="jsonl")
    p_scan.add_argument("--out", help="JSON-файл для полного отчёта")
    p_scan.set_defaults(func=cmd_scan)

    p_mask = sub.add_parser("pseudonymize", help="Замаскировать ПДн в логе")
    p_mask.add_argument("--input", required=True)
    p_mask.add_argument("--format", choices=["jsonl", "json", "txt", "dir"], default="jsonl")
    p_mask.add_argument("--out", required=True)
    p_mask.set_defaults(func=cmd_pseudonymize)

    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
