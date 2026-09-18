#!/usr/bin/env python3
"""Extract or normalize GitHub Copilot Chat summary records."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

REQUIRED = ("Model", "Prompt", "Credit", "Date")
OUTPUT_FIELDS = (*REQUIRED, "WorkspacePath", "SessionId")
PROMPT_LIMIT = 500


def expanded_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def normalize_prompt(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:PROMPT_LIMIT] or None


def sqlite_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for pattern in ("*.db", "*.sqlite", "*.sqlite3")
        for path in root.rglob(pattern)
        if path.is_file()
    )


def sqlite_records(path: Path) -> tuple[list[dict[str, str | None]], list[str]]:
    """Read a compatible summary table without assuming a fixed DB schema."""
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        ]
        for table in tables:
            columns = [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]
            lookup = {normalized_header(column): column for column in columns}
            if not all(normalized_header(column) in lookup for column in REQUIRED):
                continue
            selected = [lookup[normalized_header(column)] for column in REQUIRED]
            quoted = ", ".join(f'"{column}"' for column in selected)
            rows = connection.execute(f'SELECT {quoted} FROM "{table}"')
            return [
                {field.casefold(): value for field, value in zip(REQUIRED, row)}
                for row in rows
            ], columns
    return [], []


def apply_session_update(requests: list[dict], update: dict) -> None:
    path = update.get("k")
    if not isinstance(path, list) or len(path) < 3 or path[0] != "requests":
        return
    request_index = path[1]
    if not isinstance(request_index, int) or request_index >= len(requests):
        return
    target = requests[request_index]
    for key in path[2:-1]:
        if not isinstance(target, dict):
            return
        target = target.setdefault(key, {})
    if isinstance(target, dict):
        target[path[-1]] = update.get("v")


def session_records(path: Path) -> list[dict[str, str | None]]:
    requests: list[dict] = []
    with path.open("r", encoding="utf-8-sig") as source:
        for line in source:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("kind") == 0:
                value = event.get("v", {})
                requests = value.get("requests", []) if isinstance(value, dict) else []
            elif event.get("kind") == 2 and event.get("k") == ["requests"]:
                value = event.get("v", [])
                if isinstance(value, list):
                    requests.extend(item for item in value if isinstance(item, dict))
            elif event.get("kind") == 1:
                apply_session_update(requests, event)

    records = []
    for source_record, request in enumerate(requests):
        if not isinstance(request, dict):
            continue
        message = request.get("message", {})
        if not isinstance(message, dict):
            message = {}
        credit = request.get("copilotCredits", request.get("credit"))
        timestamp = request.get("timestamp") or request.get("responseTimestamp")
        if isinstance(timestamp, (int, float)):
            date = datetime.fromtimestamp(timestamp / 1000).astimezone().strftime(
                "%m/%d/%Y %H:%M"
            )
        else:
            date = str(timestamp) if timestamp else None
        records.append(
            {
                "model": request.get("modelId"),
                "prompt": normalize_prompt(message.get("text")),
                "credit": str(credit) if credit is not None else None,
                "date": date,
                "session_id": path.stem,
                "source_file": str(path),
                "source_record": source_record,
                "source_keys": sorted(request.keys()),
                "credit_key": (
                    "copilotCredits"
                    if "copilotCredits" in request
                    else "credit" if "credit" in request else None
                ),
                "timestamp_key": (
                    "timestamp"
                    if "timestamp" in request
                    else "responseTimestamp" if "responseTimestamp" in request else None
                ),
            }
        )
    return records


def workspace_storage_records(root: Path) -> list[dict[str, str | None]]:
    records: list[dict[str, str | None]] = []
    for workspace in sorted(path for path in root.iterdir() if path.is_dir()):
        copilot_folder = workspace / "GitHub.copilot-chat"
        chat_sessions = workspace / "chatSessions"
        if not (workspace / "state.vscdb").is_file() or not (
            copilot_folder.is_dir() or chat_sessions.is_dir()
        ):
            continue
        session_files = sorted(chat_sessions.glob("*.jsonl"))
        for session in session_files:
            for record in session_records(session):
                record["workspace_path"] = str(workspace)
                records.append(record)
    return records


def read_source(path: Path) -> tuple[list[dict[str, str | None]], list[str]]:
    if path.is_dir():
        if any(
            (child / "state.vscdb").is_file()
            and (
                (child / "GitHub.copilot-chat").is_dir()
                or (child / "chatSessions").is_dir()
            )
            for child in path.iterdir()
            if child.is_dir()
        ):
            records = workspace_storage_records(path)
            if records:
                return records, ["Model", "Prompt", "Credit", "Date"]
            raise ValueError(f"No Copilot chat sessions found under workspace storage {path}")
        for database in sqlite_paths(path):
            records, headers = sqlite_records(database)
            if records:
                return records, headers
        root = path.parent if path.name == "GitHub.copilot-chat" else path
        session_files = sorted((root / "chatSessions").glob("*.jsonl"))
        records = [record for session in session_files for record in session_records(session)]
        if records:
            return records, ["Model", "Prompt", "Credit", "Date"]
        raise ValueError(f"No SQLite table with Model, Prompt, Credit, and Date found under {path}")

    if path.suffix.casefold() in {".db", ".sqlite", ".sqlite3"}:
        records, headers = sqlite_records(path)
        if not records:
            raise ValueError(f"No SQLite table with Model, Prompt, Credit, and Date found in {path}")
        return records, headers

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        sample = source.read(4096)
        source.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(source, dialect=dialect)
        headers = reader.fieldnames or []
        return [
            {key.casefold(): (row.get(key) or "").strip() or None for key in headers}
            for row in reader
        ], headers


def normalized_header(value: str | None) -> str:
    return (value or "").lstrip("\ufeff").strip().casefold()


def parse_date(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def chronological_key(record: dict[str, str | None]) -> tuple[int, str]:
    value = record.get("date") or ""
    for format_string in ("%m/%d/%Y %H:%M", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return (0, datetime.strptime(value, format_string).isoformat())
        except ValueError:
            continue
    return (1, value)


def is_current_month(record: dict[str, str | None]) -> bool:
    value = record.get("date") or ""
    try:
        date = datetime.strptime(value, "%m/%d/%Y %H:%M")
    except ValueError:
        return False
    now = datetime.now()
    return date.year == now.year and date.month == now.month


def parse_credit_value(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def credit_text(value: object) -> str:
    parsed = parse_credit_value(value)
    if parsed is None:
        return ""
    rounded = parsed.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return format(rounded, "f")


def write_excel_summary(
    records: list[dict[str, str | None]], output_path: Path, sort_by_date: bool = False
) -> None:
    from openpyxl import Workbook

    if sort_by_date:
        records = sorted(records, key=chronological_key)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Chat Summary"
    worksheet.append(OUTPUT_FIELDS)
    for record in records:
        row = [
            record.get("model") or "",
            record.get("prompt") or "",
            parse_credit_value(record.get("credit")),
            record.get("date") or "",
            record.get("workspace_path") or "",
            record.get("session_id") or "",
        ]
        worksheet.append(row)
    for cell in worksheet[1]:
        cell.font = cell.font.copy(bold=True)
    for cell in worksheet["C"][1:]:
        if cell.value is not None:
            cell.number_format = "0.00000000000000000"
    worksheet.freeze_panes = "A2"
    workbook.save(output_path)


def session_summary_records(
    records: list[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    summaries: dict[str, dict[str, str | None]] = {}
    for index, record in enumerate(records):
        session_id = record.get("session_id") or f"<record-{index}>"
        summary = summaries.get(session_id)
        if summary is None:
            summary = {
                "model": record.get("model"),
                "prompt": record.get("prompt"),
                "credit": "0",
                "date": record.get("date"),
                "workspace_path": record.get("workspace_path"),
                "session_id": record.get("session_id"),
            }
            summaries[session_id] = summary
        elif not summary.get("prompt") and record.get("prompt"):
            summary["prompt"] = record["prompt"]

        credit = parse_credit_value(record.get("credit"))
        if credit is not None:
            total = parse_credit_value(summary.get("credit")) or Decimal("0")
            summary["credit"] = str(total + credit)

    return list(summaries.values())


def write_csv_summary(records: list[dict[str, str | None]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "Model": record.get("model") or "",
                    "Prompt": record.get("prompt") or "",
                    "Credit": credit_text(record.get("credit")),
                    "Date": record.get("date") or "",
                    "WorkspacePath": record.get("workspace_path") or "",
                    "SessionId": record.get("session_id") or "",
                }
            )


def reconciliation_outputs(
    raw_records: list[dict[str, str | None]], output_directory: Path
) -> None:
    duplicate_keys = Counter(
        (
            record.get("model"),
            record.get("prompt"),
            record.get("credit"),
            record.get("date"),
            record.get("workspace_path"),
            record.get("session_id"),
        )
        for record in raw_records
    )
    duplicate_seen: Counter[tuple] = Counter()
    category_counts: Counter[str] = Counter()
    category_totals: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    model_totals: Counter[str] = Counter()
    date_counts: Counter[str] = Counter()
    date_totals: Counter[str] = Counter()
    model_date_counts: Counter[tuple[str, str]] = Counter()
    model_date_totals: Counter[tuple[str, str]] = Counter()
    raw_total = Decimal("0")
    current_month_total = Decimal("0")
    detail_records: list[dict[str, object]] = []

    for source_row, record in enumerate(raw_records, start=2):
        credit = parse_credit_value(record.get("credit"))
        if credit is not None:
            raw_total += credit
            if is_current_month(record):
                current_month_total += credit

        duplicate_key = (
            record.get("model"),
            record.get("prompt"),
            record.get("credit"),
            record.get("date"),
            record.get("workspace_path"),
            record.get("session_id"),
        )
        duplicate_seen[duplicate_key] += 1
        duplicate_candidate = duplicate_keys[duplicate_key] > 1

        if not record.get("prompt"):
            category = "skipped_missing_prompt"
        elif not record.get("date") or not record.get("model"):
            category = "skipped_missing_date_or_model"
        elif credit is None and is_current_month(record):
            category = "skipped_missing_credit"
        elif is_current_month(record):
            category = "included_chat_record"
        else:
            category = "other_copilot_usage_record"

        category_counts[category] += 1
        if credit is not None:
            category_totals[category] += credit
            if category == "included_chat_record":
                model = record.get("model") or "<blank>"
                date = (record.get("date") or "<blank>")[:10]
                model_counts[model] += 1
                model_totals[model] += credit
                date_counts[date] += 1
                date_totals[date] += credit
                model_date_key = (model, date)
                model_date_counts[model_date_key] += 1
                model_date_totals[model_date_key] += credit
        detail_records.append(
            {
                "source_row": source_row,
                "category": category,
                "duplicate_candidate": duplicate_candidate,
                "model": record.get("model"),
                "prompt": record.get("prompt"),
                "credit": record.get("credit"),
                "date": record.get("date"),
                "workspace_path": record.get("workspace_path"),
                "session_id": record.get("session_id"),
                "source_file": record.get("source_file"),
                "source_record": record.get("source_record"),
                "source_keys": record.get("source_keys"),
                "credit_key": record.get("credit_key"),
                "timestamp_key": record.get("timestamp_key"),
            }
        )

    duplicate_rows = [item for item in detail_records if item["duplicate_candidate"]]
    report = {
        "raw_record_count": len(raw_records),
        "raw_database_total": str(raw_total),
        "raw_database_total_current_month": str(current_month_total),
        "current_month": datetime.now().strftime("%Y-%m"),
        "categories": {
            category: {
                "record_count": category_counts[category],
                "credit_total": str(category_totals[category]),
            }
            for category in sorted(category_counts)
        },
        "by_model": {key: str(model_totals[key]) for key in sorted(model_totals)},
        "by_date": {key: str(date_totals[key]) for key in sorted(date_totals)},
        "duplicate_candidates": {
            "record_count": len(duplicate_rows),
            "credit_total": str(
                sum(
                    (
                        parse_credit_value(item["credit"]) or Decimal("0")
                        for item in duplicate_rows
                    ),
                    Decimal("0"),
                )
            ),
            "excess_record_count": sum(
                count - 1 for count in duplicate_keys.values() if count > 1
            ),
        },
        "detail_file": "reconciliation_records.jsonl",
    }

    with (output_directory / "reconciliation_report.json").open(
        "w", encoding="utf-8"
    ) as target:
        json.dump(report, target, indent=2)
    with (output_directory / "reconciliation_records.jsonl").open(
        "w", encoding="utf-8"
    ) as target:
        for detail in detail_records:
            target.write(json.dumps(detail, ensure_ascii=True) + "\n")
    with (output_directory / "reconciliation_records.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        fields = (
            "source_row",
            "category",
            "duplicate_candidate",
            "model",
            "prompt",
            "credit",
            "date",
            "workspace_path",
            "source_file",
            "source_record",
            "source_keys",
            "credit_key",
            "timestamp_key",
            "session_id",
        )
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        for detail in detail_records:
            writer.writerow(
                {
                    **detail,
                    "source_keys": json.dumps(detail["source_keys"] or []),
                    "credit": credit_text(detail["credit"]),
                }
            )
    with (output_directory / "credit_totals_by_model.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(target, fieldnames=("Model", "RecordCount", "CreditTotal"))
        writer.writeheader()
        for model in sorted(model_totals):
            writer.writerow(
                {
                    "Model": model,
                    "RecordCount": model_counts[model],
                    "CreditTotal": credit_text(model_totals[model]),
                }
            )
    with (output_directory / "credit_totals_by_date.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(target, fieldnames=("Date", "RecordCount", "CreditTotal"))
        writer.writeheader()
        for date in sorted(date_totals, key=lambda value: chronological_key({"date": value})):
            writer.writerow(
                {
                    "Date": date,
                    "RecordCount": date_counts[date],
                    "CreditTotal": credit_text(date_totals[date]),
                }
            )
    with (output_directory / "credit_totals_by_model_date.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(
            target, fieldnames=("Model", "Date", "RecordCount", "CreditTotal")
        )
        writer.writeheader()
        for model, date in sorted(
            model_date_totals,
            key=lambda item: (item[0], chronological_key({"date": item[1]})),
        ):
            writer.writerow(
                {
                    "Model": model,
                    "Date": date,
                    "RecordCount": model_date_counts[(model, date)],
                    "CreditTotal": credit_text(model_date_totals[(model, date)]),
                }
            )


def timestamped_summary_path(output_directory: Path) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    return output_directory / timestamp / "chat_summary.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=expanded_path,
        help="CSV file, SQLite database, or GitHub.copilot-chat workspace folder",
    )
    parser.add_argument(
        "output_directory",
        type=expanded_path,
        nargs="?",
        default=None,
        help="Output directory (default: chatlog/csv)",
    )
    args = parser.parse_args()
    output_path = timestamped_summary_path(args.output_directory or Path("chatlog") / "csv")

    raw_records, raw_headers = read_source(args.input)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reconciliation_outputs(raw_records, output_path.parent)
    raw_records = [record for record in raw_records if is_current_month(record)]
    raw_records.sort(key=chronological_key)
    header_map = {normalized_header(name): name for name in raw_headers}
    missing = [name for name in REQUIRED if normalized_header(name) not in header_map]
    records, malformed = [], []
    for row_number, row in enumerate(raw_records, start=2):
        record = {
            "source_row": row_number,
            "model": row.get("model"),
            "prompt": normalize_prompt(row.get("prompt")),
            "credit": row.get("credit"),
            "date": row.get("date"),
            "workspace_path": row.get("workspace_path"),
            "session_id": row.get("session_id"),
        }
        record["parsed_date"] = parse_date(record["date"])
        records.append(record)

    write_csv_summary(records, output_path)
    write_excel_summary(records, output_path.with_name("chat_summary.xlsx"))
    write_excel_summary(
        records, output_path.with_name("chat_summary_sort.xlsx"), sort_by_date=True
    )
    session_records = session_summary_records(records)
    write_csv_summary(
        session_records, output_path.with_name("summary_by_session.csv")
    )
    write_excel_summary(
        session_records, output_path.with_name("summary_by_session.xlsx")
    )
    print(f"Wrote {len(records)} record(s) to {output_path}")


if __name__ == "__main__":
    main()
