#!/usr/bin/env python3
"""cyrillic-log-analyzer.

Детектор и восстановитель текста с перемешанной кодировкой и/или транслитом.

Поддерживает:
  - mojibake UTF-8→CP1251 / UTF-8→Latin-1 (детект + round-trip fix)
  - смешанные кодировки в одном файле (построчно)
  - транслит → кириллица (несколько схем: Volapuk с цифрами, ГОСТ-like, ICAO)
  - переключение раскладки qwerty↔йцук (забытый Shift/CapsLock)

Без внешних зависимостей — только Python 3.10+ stdlib.

Подкоманды:
  analyze   отчёт по логу/файлу: статус каждой строки, агрегаты, рекомендации
  fix       применить авто-исправления (mojibake + layout) и вывести на stdout
  translit  транслит → кириллица
  layout    переключить раскладку qwerty↔йцук

Выход report-команды — markdown, fix/translit/layout — текст на stdout.

Примеры:
  python analyze.py analyze logs/app.log
  python analyze.py fix logs/app.log > fixed.log
  python analyze.py translit --scheme volapuk <<< "Privet, kak dela?"
  cat logs/*.log | python analyze.py analyze -
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# === Кодировка ===

CYR_LO = "\u0400"
CYR_HI = "\u04ff"
LATIN_SUPP_LO = "\u00c0"  # À
LATIN_SUPP_HI = "\u00ff"  # ÿ — диапазон mojibake-артефактов


def is_cyr(c: str) -> bool:
    return CYR_LO <= c <= CYR_HI


def is_latin_supp(c: str) -> bool:
    return LATIN_SUPP_LO <= c <= LATIN_SUPP_HI


def cyr_ratio(s: str) -> float:
    if not s:
        return 0.0
    n = sum(1 for c in s if is_cyr(c))
    return n / len(s)


def lower_cyr_count(s: str) -> int:
    """Строчная кириллица (а-я). В CP1251-mojibake её почти нет — там UPPERCASE Р/С как lead bytes."""
    return sum(1 for c in s if "\u0430" <= c <= "\u04ff")


def lead_byte_count(s: str) -> int:
    """'Р' и 'С' (CP1251 0xD0/0xD1) или 'Ð'/'Ñ' (Latin-1 0xC3+0x90/0x91) — UTF-8 lead bytes для Cyrillic.

    В нормальном русском они составляют ~3-5% букв, в mojibake — >15% (каждый кириллический символ даёт один lead).
    """
    return sum(1 for c in s if c in "РСÐÑ")


def latin_alpha_ratio(s: str) -> float:
    if not s:
        return 0.0
    n = sum(1 for c in s if c.isascii() and c.isalpha())
    return n / len(s)


def latin_supp_ratio(s: str) -> float:
    """Доля символов из Latin-1 Supplement — маркер mojibake (латиницы варианты)."""
    if not s:
        return 0.0
    n = sum(1 for c in s if is_latin_supp(c))
    return n / len(s)


def _looks_better_as_russian(fixed: str, original: str) -> bool:
    """Эвристика: fixed выглядит как нормальный русский текст сильнее, чем original."""
    # После fix должно быть больше строчной кириллицы (а-я)
    if lower_cyr_count(fixed) <= lower_cyr_count(original) + 2:
        return False
    # Lead-byte density: в mojibake аномально высокая (>15% нетипичных Р/С/Ð/Ñ)
    if lead_byte_count(fixed) > 0 and lead_byte_count(fixed) > lead_byte_count(original):
        return False
    return True


def try_fix_cp1251_mojibake(text: str) -> str | None:
    """Если текст — UTF-8 прочитанный как CP1251, возвращает исправленный.

    UTF-8 lead-байты для Cyrillic 0xD0/0xD1 в CP1251 отображаются в 'Р'/'С',
    а continuation bytes 0x80-0xBF — в экзотику из верхнего диапазона CP1251.
    Round-trip через encode('cp1251').decode('utf-8') восстанавливает исходник.
    """
    if "Р" not in text and "С" not in text:
        return None
    try:
        fixed = text.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return fixed if _looks_better_as_russian(fixed, text) else None


def try_fix_latin1_mojibake(text: str) -> str | None:
    """Если текст — UTF-8 прочитанный как Latin-1 (ISO-8859-1).

    Маркеры: 'Ð' (U+00D0) и 'Ñ' (U+00D1) — UTF-8 lead bytes 0xC3 0x90 / 0xC3 0x91
    в Latin-1-прочтении.
    """
    if "Ð" not in text and "Ñ" not in text:
        return None
    try:
        fixed = text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return fixed if _looks_better_as_russian(fixed, text) else None


# === Транслитерация ===

# Диграфы/триграфы — порядок важен: длинные замены вперёд.
# Хранится lower-case, case восстанавливается в translit_apply().
# ВНИМАНИЕ: 'sch' не включён — он неоднозначен (Schmidt→Шмидт vs school→скул).
# Для щ всегда используется однозначный 'shch'.
_MULTI: list[tuple[str, str]] = [
    ("shch", "щ"),
    ("zh",   "ж"),
    ("kh",   "х"),
    ("ts",   "ц"),
    ("ch",   "ч"),
    ("sh",   "ш"),
    ("ya",   "я"),
    ("yu",   "ю"),
    ("yo",   "ё"),
    ("ye",   "е"),
    ("ja",   "я"),
    ("ju",   "ю"),
    ("jo",   "ё"),
    ("aj",   "ай"),
    ("oj",   "ой"),
    ("uj",   "уй"),
    ("ej",   "ей"),
    ("ij",   "ий"),
    ("yj",   "ый"),
    ("y'",   "ы"),
    ("''",   "ъ"),
]

# Volapuk с цифрами (хакерский транслит 90-х)
_VOLAPUK_DIGITS: dict[str, str] = {
    "4": "ч",
    "6": "ш",
    "^": "щ",
}

# Однобуквенные соответствия — Latin → Cyrillic.
# Неоднозначные: w=в (ГОСТ) / ш (английский-like); y=ы / й / и; x=кс / х.
# По умолчанию берём самый частотный вариант в русском нетранслите.
_SINGLES_LOWER: dict[str, str] = {
    "a": "а", "b": "б", "v": "в", "g": "г", "d": "д", "e": "е",
    "z": "з", "i": "и", "j": "й", "k": "к", "l": "л", "m": "м",
    "n": "н", "o": "о", "p": "п", "r": "р", "s": "с", "t": "т",
    "u": "у", "f": "ф", "h": "х", "w": "в", "y": "ы", "x": "х",
    "c": "ц", "`": "ъ", "'": "ь",
}

# Неоднозначные буквы, которые стоит подсветить в отчёте
AMBIGUOUS_LETTERS = {"w", "y", "x", "j", "c", "h"}


def _preserve_case(match: str, lower_target: str) -> str:
    if match.isupper():
        return lower_target.upper()
    if match[0].isupper() and (len(match) == 1 or match[1:].islower()):
        return lower_target[0].upper() + lower_target[1:]
    return lower_target


_MULTI_PATTERN = re.compile(
    "|".join(re.escape(k) for k, _ in _MULTI),
    re.IGNORECASE,
)
_MULTI_MAP: dict[str, str] = {k: v for k, v in _MULTI}


def translit_to_cyrillic(text: str, scheme: str = "auto") -> str:
    """Конвертация транслита в кириллицу.

    scheme:
      'auto'     — диграфы + однобуквенные (безопасно: цифры остаются цифрами)
      'volapuk'  — то же + замена 4→ч, 6→ш, ^→щ (хакерский транслит 90-х)
      'gost'     — псевдоним 'auto' (для совместимости по имени)
    """
    if scheme == "volapuk":
        for latin, cyr in _VOLAPUK_DIGITS.items():
            text = text.replace(latin, cyr)

    def repl_multi(m: re.Match) -> str:
        matched = m.group(0)
        target = _MULTI_MAP[matched.lower()]
        return _preserve_case(matched, target)

    text = _MULTI_PATTERN.sub(repl_multi, text)

    out_chars: list[str] = []
    for c in text:
        if c.lower() in _SINGLES_LOWER:
            target = _SINGLES_LOWER[c.lower()]
            out_chars.append(_preserve_case(c, target))
        else:
            out_chars.append(c)
    return "".join(out_chars)


# === Раскладка клавиатуры ===

QWERTY_TO_YCUK: dict[str, str] = {
    "`": "ё", "q": "й", "w": "ц", "e": "у", "r": "к", "t": "е", "y": "н",
    "u": "г", "i": "ш", "o": "щ", "p": "з", "[": "х", "]": "ъ",
    "a": "ф", "s": "ы", "d": "в", "f": "а", "g": "п", "h": "р", "j": "о",
    "k": "л", "l": "д", ";": "ж", "'": "э",
    "z": "я", "x": "ч", "c": "с", "v": "м", "b": "и", "n": "т", "m": "ь",
    ",": "б", ".": "ю", "/": ".",
}
YCUK_TO_QWERTY: dict[str, str] = {v: k for k, v in QWERTY_TO_YCUK.items()}


def switch_layout(text: str, direction: str = "auto") -> str:
    """Переключить раскладку.

    direction: 'auto' (по большинству), 'lat→cyr', 'cyr→lat'.
    """
    if direction == "auto":
        # Если в тексте латиницы больше, чем кириллицы, и латиница выглядит «по-русски»
        # — вероятно, забыли переключить на русский.
        lat = sum(1 for c in text if c.isascii() and c.isalpha())
        cyr = sum(1 for c in text if is_cyr(c))
        direction = "lat→cyr" if lat > cyr else "cyr→lat"

    if direction == "lat→cyr":
        table = QWERTY_TO_YCUK
    else:
        table = YCUK_TO_QWERTY

    out: list[str] = []
    for c in text:
        lower = c.lower()
        if lower in table:
            target = table[lower]
            out.append(target.upper() if c.isupper() else target)
        else:
            out.append(c)
    return "".join(out)


# === Детектор статуса строки ===

TRANSPLIT_HINT_RE = re.compile(
    r"\b(sh|ch|zh|ya|yu|yo|kh|ts|shch|aj|oj|uj|ej|ij|yj|ja|ju|jo)\b",
    re.IGNORECASE,
)
ENGLISH_HINT_RE = re.compile(
    r"\b(the|and|for|with|that|this|from|have|they|will|your|not|but|you|all|any|can|had|her|was|one|our|out|are|has|him|his|how|its|may|new|now|old|see|too|use|way|who|did|get|let|say|she|too|them|then|think|take|come|could|would|make|know|there|their|what|when|where|which|while|about|after|again|before|between|during|through)\b",
    re.IGNORECASE,
)


@dataclass
class LineClassification:
    status: str  # clean_cyr | clean_lat | mixed | mojibake | translit_likely | empty
    detail: str = ""
    fixed: str | None = None


def classify_line(line: str) -> LineClassification:
    stripped = line.strip()
    if not stripped:
        return LineClassification("empty")

    cyr = sum(1 for c in stripped if is_cyr(c))
    lat_alpha = sum(1 for c in stripped if c.isascii() and c.isalpha())
    total_alpha = cyr + lat_alpha
    if total_alpha == 0:
        return LineClassification("empty", "no alpha chars")

    cyr_share = cyr / total_alpha
    lat_share = lat_alpha / total_alpha

    # Сначала mojibake — round-trip сам валидирует через _looks_better_as_russian.
    # Проверка дешёвая: быстрый фильтр по наличию lead-byte маркеров внутри try_fix_*.
    fixed = try_fix_cp1251_mojibake(stripped)
    if fixed is not None:
        return LineClassification("mojibake", "utf8→cp1251", fixed)
    fixed = try_fix_latin1_mojibake(stripped)
    if fixed is not None:
        return LineClassification("mojibake", "utf8→latin1", fixed)

    # Чистая кириллица
    if cyr_share > 0.85:
        return LineClassification("clean_cyr")

    # Чистая латиница
    if lat_share > 0.85:
        # Латиница с типичными транслит-диграфами — скорее всего транслит
        if TRANSPLIT_HINT_RE.search(stripped) and not ENGLISH_HINT_RE.search(stripped):
            return LineClassification("translit_likely")
        # Латиница без английских стоп-слов и с -yj/-ij/-aj окончаниями — транслит
        if re.search(r"\b\w+(yj|ij|aj|oj|uj|ya|yu|ech|ck)\b", stripped, re.IGNORECASE):
            return LineClassification("translit_likely")
        # Чистый английский
        if ENGLISH_HINT_RE.search(stripped):
            return LineClassification("clean_lat", "english")
        return LineClassification("clean_lat", "unknown-lang")

    # Смешанный
    return LineClassification("mixed", f"cyr={cyr_share:.0%} lat={lat_share:.0%}")


# === Парсинг ввода ===

def iter_lines(input_path: Path) -> Iterable[tuple[int, str]]:
    """Читает файл построчно. Большие файлы — без загрузки в память."""
    if str(input_path) == "-":
        for i, line in enumerate(sys.stdin, 1):
            yield i, line.rstrip("\n")
        return
    with input_path.open("r", encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            yield i, line.rstrip("\n")


# === Агрегация ===

@dataclass
class LogStats:
    total_lines: int = 0
    empty: int = 0
    clean_cyr: int = 0
    clean_lat: int = 0
    mixed: int = 0
    mojibake: int = 0
    translit_likely: int = 0
    mojibake_kinds: Counter = field(default_factory=Counter)
    ambiguous_letter_hits: Counter = field(default_factory=Counter)
    examples: dict[str, list[tuple[int, str, str | None]]] = field(default_factory=dict)

    def record(self, line_no: int, line: str, cls: LineClassification) -> None:
        self.total_lines += 1
        if cls.status == "empty":
            self.empty += 1
            return
        setattr(self, cls.status.replace("-", "_"), getattr(self, cls.status.replace("-", "_")) + 1)
        if cls.status == "mojibake":
            self.mojibake_kinds[cls.detail] += 1
        if cls.status == "translit_likely":
            for m in re.finditer(r"[a-zA-Z]", line):
                low = m.group(0).lower()
                if low in AMBIGUOUS_LETTERS:
                    self.ambiguous_letter_hits[low] += 1
        # up to 3 examples per status
        bucket = self.examples.setdefault(cls.status, [])
        if len(bucket) < 3:
            snippet = line.strip()[:120]
            bucket.append((line_no, snippet, cls.fixed))


def score_log(stats: LogStats) -> tuple[int, str]:
    """0-16: насколько лог «болен» кириллическими проблемами."""
    non_empty = max(stats.total_lines - stats.empty, 1)
    mojibake_pct = stats.mojibake / non_empty * 100
    translit_pct = stats.translit_likely / non_empty * 100
    mixed_pct = stats.mixed / non_empty * 100

    score = 0
    score += min(4, int(mojibake_pct // 5))           # 0-4 за mojibake
    score += min(4, int(translit_pct // 10))          # 0-4 за транслит
    score += min(4, int(mixed_pct // 10))             # 0-4 за смешанность
    if len(stats.mojibake_kinds) >= 2:                # несколько видов mojibake — хуже
        score += 2
    score = min(score, 12)

    if score <= 4:
        verdict = "✅ лог чистый"
    elif score <= 9:
        verdict = "⚠️ есть проблемы — стоит прогнать fix"
    else:
        verdict = "🚨 критический — данные теряются"
    return score, verdict


# === Подкоманды ===

def cmd_analyze(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    stats = LogStats()

    for line_no, line in iter_lines(input_path):
        cls = classify_line(line)
        stats.record(line_no, line, cls)

    score, verdict = score_log(stats)
    non_empty = stats.total_lines - stats.empty

    print("# Cyrillic-Log-Analyzer Report\n")
    print(f"## Источник\n- Файл: `{args.input}`")
    print(f"- Строк всего: {stats.total_lines} (непустых: {non_empty})\n")

    print("## Сводка")
    print(f"- Mojibake: **{stats.mojibake}** ({stats.mojibake / max(non_empty, 1):.1%})")
    print(f"- Транслит (вероятный): **{stats.translit_likely}** ({stats.translit_likely / max(non_empty, 1):.1%})")
    print(f"- Смешанные строки: **{stats.mixed}** ({stats.mixed / max(non_empty, 1):.1%})")
    print(f"- Чистая кириллица: {stats.clean_cyr}")
    print(f"- Чистая латиница: {stats.clean_lat}")
    print(f"- Общий балл: **{score} / 12** — {verdict}\n")

    if stats.mojibake_kinds:
        print("## Типы mojibake")
        print("| Тип | Строк |")
        print("|-----|-------|")
        for kind, n in stats.mojibake_kinds.most_common():
            print(f"| {kind} | {n} |")
        print()

    if stats.ambiguous_letter_hits:
        print("## Неоднозначные буквы в транслите (top-5)")
        print("Эти буквы имеют разные схемы (w=в/ш, y=ы/й/и, j=й/ж). Проверьте вручную.")
        print("| Буква | Встречаемость |")
        print("|-------|---------------|")
        for letter, n in stats.ambiguous_letter_hits.most_common(5):
            print(f"| {letter} | {n} |")
        print()

    if stats.examples:
        print("## Примеры")
        for status, bucket in stats.examples.items():
            print(f"### {status}")
            for line_no, snippet, fixed in bucket:
                print(f"- L{line_no}: `{snippet}`")
                if fixed:
                    print(f"  → `{fixed}`")
            print()

    print("## Рекомендации")
    if stats.mojibake > 0:
        print(f"- Запустите `fix {args.input} > fixed.log` — автоматически восстановит UTF-8.")
    if stats.translit_likely > 0:
        print("- Для транслита прогоните `translit --scheme volapuk` (предпросмотр обязателен — схема неоднозначна).")
    if stats.mixed > stats.clean_cyr:
        print("- Доля mixed-строк выше чистой кириллицы — проверьте, не слиплись ли разные источники в один лог.")
    if score <= 4:
        print("- Лог в порядке, вмешательство не требуется.")
    return 0


def cmd_fix(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    out = sys.stdout
    for _, line in iter_lines(input_path):
        cls = classify_line(line)
        if cls.status == "mojibake" and cls.fixed is not None:
            out.write(cls.fixed + "\n")
        else:
            out.write(line + "\n")
    out.flush()
    return 0


def cmd_translit(args: argparse.Namespace) -> int:
    text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8", errors="replace")
    sys.stdout.write(translit_to_cyrillic(text, scheme=args.scheme))
    sys.stdout.flush()
    return 0


def cmd_layout(args: argparse.Namespace) -> int:
    text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8", errors="replace")
    sys.stdout.write(switch_layout(text, direction=args.direction))
    sys.stdout.flush()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cyrillic-log-analyzer",
        description="Детектор и восстановитель текста с перемешанной кодировкой/транслитом.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_analyze = sub.add_parser("analyze", help="отчёт по логу (default-команда)")
    p_analyze.add_argument("input", help="путь к файлу или '-' для stdin")
    p_analyze.set_defaults(func=cmd_analyze)

    p_fix = sub.add_parser("fix", help="авто-исправление mojibake, вывод на stdout")
    p_fix.add_argument("input", help="путь к файлу или '-' для stdin")
    p_fix.set_defaults(func=cmd_fix)

    p_tr = sub.add_parser("translit", help="транслит → кириллица (stdin → stdout)")
    p_tr.add_argument("input", nargs="?", default="-", help="путь к файлу или '-' для stdin")
    p_tr.add_argument(
        "--scheme",
        choices=["auto", "gost", "volapuk"],
        default="auto",
        help="схема транслитерации (default: auto)",
    )
    p_tr.set_defaults(func=cmd_translit)

    p_layout = sub.add_parser("layout", help="переключить раскладку qwerty↔йцук")
    p_layout.add_argument("input", nargs="?", default="-", help="путь к файлу или '-' для stdin")
    p_layout.add_argument(
        "--direction",
        choices=["auto", "lat→cyr", "cyr→lat"],
        default="auto",
        help="направление переключения (default: auto)",
    )
    p_layout.set_defaults(func=cmd_layout)

    return p


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
