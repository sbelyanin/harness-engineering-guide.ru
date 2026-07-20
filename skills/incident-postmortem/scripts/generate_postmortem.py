#!/usr/bin/env python3
"""generate_postmortem.py — создаёт markdown template для постмортема.

Заполняет метаданные (date, incident_id, severity), выводит в stdout
или в файл. Только Python stdlib.

Использование:
    python3 generate_postmortem.py --title "..." --severity SEV-2
    python3 generate_postmortem.py --title "..." --severity SEV-1 \\
        --lead "@oncall" --duration "1h 12m" --output postmortems/foo.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys


TEMPLATE = """\
# Postmortem: {title}

**Date:** {date}  
**Severity:** {severity}  
**Incident duration:** {duration}  
**Lead:** {lead}  
**Status:** Draft  
**Incident ID:** {incident_id}

## Summary

<1-2 параграфа для менеджера/stakeholder'а: что произошло, какой impact,
сколько длилось. Без технических деталей — что случилось на человеческом
языке. Кто затронут, что не работало.>

## Impact

- **Пользователей затронуто:** ~N (или % от DAU)
- **Запросов упало:** ~M
- **SLI нарушен:** <success rate / latency / eval pass rate>
- **Error budget:** сожжено X% (см. /guide/alerting-and-slo)
- **Cost impact:** $X (если применимо)
- **External communication:** <твит/status page/internal>

## Timeline (UTC)

Все времена в UTC, с точностью до минуты.

- **HH:MM** — Первые признаки (метрика отклонилась от baseline)
- **HH:MM** — Alert triggered: `<alert name>`, ack в <Xm
- **HH:MM** — Diagnosis: <что думали сначала>
- **HH:MM** — Mitigation попытка 1: <action>, результат
- **HH:MM** — Recovery confirmed: метрики вернулись в норму
- **HH:MM** — Post-incident review scheduled

## Root Cause

<Техническое объяснение: что именно сломалось и почему. Цепочка «как мы
сюда попали». Если несколько факторов — нумеруйте.>

1. <factor 1>
2. <factor 2>
3. <factor 3>

## What Went Well

- <Что сработало, как задумано>
- <Какая автоматизация спасла>
- <Traces дали быстрый diagnosis>

## What Went Poorly

- <Что задержало recovery>
- <Какие инструменты подвели>
- <Alert был слишком поздним / ранним>
- <Runbook отсутствовал / устарел>

## Action Items

Конкретные, с владельцем и сроком. Без владельца = не будет сделано.

- [ ] **(Owner: @name, due: YYYY-MM-DD)** Fix <root cause>
- [ ] **(Owner: @name, due: YYYY-MM-DD)** Add runbook for <scenario>
- [ ] **(Owner: @name, due: YYYY-MM-DD)** Add metric/alert for <early detection>
- [ ] **(Owner: @name, due: YYYY-MM-DD)** Eval case covering <regression>

## Lessons Learned

<Что изменим в процессах/культуре. Не action items (те конкретные), а
принципы.>

## Appendix

- Ссылки на traces: <trace_ids>
- Логи инцидента: <link to dashboard>
- Alert definition: <link>
- Чат обсуждения: <link>
"""


def generate_incident_id(date: dt.date, salt: int = 0) -> str:
    """YYYY-MM-DD-NNN, где NNN — псевдо-уникальный суффикс."""
    base = int(date.strftime("%Y%m%d"))
    suffix = ((base + salt) * 2654435761) % 1000
    return f"{date.isoformat()}-{suffix:03d}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Generate postmortem markdown template"
    )
    p.add_argument("--title", "-t", required=True, help="Incident title")
    p.add_argument(
        "--severity",
        "-s",
        required=True,
        choices=["SEV-1", "SEV-2", "SEV-3", "SEV-4"],
    )
    p.add_argument(
        "--lead",
        "-l",
        default="<TBD>",
        help="Incident lead (handle or name)",
    )
    p.add_argument(
        "--duration",
        "-d",
        default="<TBD>",
        help="Incident duration (e.g., '1h 12m')",
    )
    p.add_argument(
        "--date",
        default=None,
        help="Incident date YYYY-MM-DD (default: today)",
    )
    p.add_argument(
        "--output",
        "-o",
        default="-",
        help="Output file (default: stdout)",
    )
    args = p.parse_args(argv)

    if args.date:
        try:
            date = dt.date.fromisoformat(args.date)
        except ValueError:
            print(f"Invalid date format: {args.date}", file=sys.stderr)
            return 1
    else:
        date = dt.date.today()

    incident_id = generate_incident_id(date, salt=os.getpid())

    content = TEMPLATE.format(
        title=args.title,
        date=date.isoformat(),
        severity=args.severity,
        duration=args.duration,
        lead=args.lead,
        incident_id=incident_id,
    )

    if args.output == "-":
        sys.stdout.write(content)
    else:
        # Создаём родительскую директорию если нужно
        out_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        print(
            f"Created: {args.output} (incident_id={incident_id})",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
