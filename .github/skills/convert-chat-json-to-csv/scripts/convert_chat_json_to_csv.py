"""Convert a VS Code Copilot chat export to a flat CSV file."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def text_from_value(value: Any) -> str:
    """Return readable text from nested chat-export values."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(part for part in (text_from_value(item) for item in value) if part)
    if isinstance(value, dict):
        for key in ("text", "value", "content", "message"):
            if key in value:
                text = text_from_value(value[key])
                if text:
                    return text
    return ""


def request_text(request: dict[str, Any]) -> str:
    message = request.get("message", {})
    if isinstance(message, dict):
        text = text_from_value(message.get("text"))
        if text:
            return text
        return text_from_value(message.get("parts", []))
    return text_from_value(message)


def response_text(request: dict[str, Any]) -> str:
    responses = request.get("response", [])
    chunks: list[str] = []
    if not isinstance(responses, list):
        responses = [responses]

    for response in responses:
        if not isinstance(response, dict):
            text = text_from_value(response)
            if text:
                chunks.append(text)
            continue
        for key in ("text", "content", "message", "invocationMessage", "pastTenseMessage"):
            text = text_from_value(response.get(key))
            if text:
                chunks.append(text)

    return "\n".join(dict.fromkeys(chunks))


def metadata_values(request: dict[str, Any]) -> dict[str, str | int]:
    result = request.get("result", {})
    if not isinstance(result, dict):
        result = {}
    metadata = result.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    thinking_tokens: list[int] = []
    rounds = metadata.get("toolCallRounds", [])
    if isinstance(rounds, list):
        for round_data in rounds:
            if not isinstance(round_data, dict):
                continue
            thinking = round_data.get("thinking", {})
            if isinstance(thinking, dict) and isinstance(thinking.get("tokens"), int):
                thinking_tokens.append(thinking["tokens"])

    return {
        "cache_key": metadata.get("cacheKey", ""),
        "prompt_tokens": result.get("promptTokens", ""),
        "output_tokens": result.get("outputTokens", ""),
        "completion_tokens": result.get("completionTokens", ""),
        "request_timestamp": request.get("timestamp", ""),
        "request_model_id": request.get("modelId", ""),
        "thinking_tokens": sum(thinking_tokens),
        "thinking_token_values": ",".join(str(value) for value in thinking_tokens),
    }


def timestamped_output_path(output_directory: Path, filename: str = "chat.csv") -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")[:-3]
    return output_directory / timestamp / filename


def display_date(timestamp: Any) -> str:
    if not isinstance(timestamp, (int, float)):
        return ""
    return datetime.fromtimestamp(timestamp / 1000).astimezone().strftime("%m/%d/%Y %I:%M %p")


def summary_credit(request: dict[str, Any]) -> int:
    values = metadata_values(request)
    thinking_values = [
        int(value)
        for value in str(values["thinking_token_values"]).split(",")
        if value.strip().isdigit()
    ]
    thinking_tokens = values["thinking_tokens"]
    return int(thinking_tokens) + sum(thinking_values)


def event_log_requests(events: list[Any], input_path: Path) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for event in events:
        if not isinstance(event, dict):
            raise ValueError(f"{input_path}: JSONL event must be a JSON object")
        event_type = event.get("type")
        data = event.get("data", {})
        if not isinstance(data, dict):
            data = {}

        if event_type == "user.message":
            if current is not None:
                requests.append(current)
            current = {
                "requestId": event.get("id", ""),
                "message": {"text": data.get("content", "")},
                "response": [],
                "timestamp": event.get("timestamp", ""),
            }
        elif event_type == "assistant.message" and current is not None:
            content = data.get("content")
            if isinstance(content, str) and content:
                current["response"].append({"text": content})
        elif event_type == "assistant.turn_end" and current is not None:
            current["result"] = {"responseTimestamp": event.get("timestamp", "")}

    if current is not None:
        requests.append(current)
    return requests


def event_log_summary_requests(events: list[Any]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    user_content = ""

    for event in events:
        if not isinstance(event, dict):
            continue
        data = event.get("data", {})
        if not isinstance(data, dict):
            data = {}
        if event.get("type") == "user.message":
            user_content = data.get("content", "")
        elif event.get("type") == "assistant.message":
            requests.append(
                {
                    "requestId": event.get("id", ""),
                    "message": {"text": user_content},
                    "response": [{"text": data.get("content", "")}],
                    "timestamp": event.get("timestamp", ""),
                    "result": {"responseTimestamp": event.get("timestamp", "")},
                }
            )

    return requests


def load_jsonl_events(input_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        with input_path.open("r", encoding="utf-8-sig") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError(
                        f"{input_path}: line {line_number} must contain a JSON object"
                    )
                events.append(event)
    except json.JSONDecodeError as error:
        raise ValueError(f"{input_path}: invalid JSON ({error})") from error
    return events


def is_event_log(events: list[dict[str, Any]]) -> bool:
    return any(isinstance(event.get("type"), str) and "data" in event for event in events)


def load_summary_requests(input_path: Path) -> list[Any]:
    if input_path.suffix.lower() != ".jsonl":
        return load_requests(input_path)
    events = load_jsonl_events(input_path)
    if is_event_log(events):
        return event_log_summary_requests(events)
    return events


def load_requests(input_path: Path) -> list[Any]:
    if input_path.suffix.lower() == ".jsonl":
        events = load_jsonl_events(input_path)
        return event_log_requests(events, input_path) if is_event_log(events) else events

    try:
        with input_path.open("r", encoding="utf-8-sig") as source:
            document = json.load(source)
    except json.JSONDecodeError as error:
        raise ValueError(f"{input_path}: invalid JSON ({error})") from error

    requests = document.get("requests") if isinstance(document, dict) else None
    if not isinstance(requests, list):
        raise ValueError(
            f"{input_path}: expected a VS Code chat export with a top-level 'requests' array"
        )
    return requests


def write_summary(input_path: Path, output_path: Path) -> int:
    requests = load_summary_requests(input_path)

    with output_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["Model", "Prompt", "Credit", "Date"])
        writer.writeheader()
        for request in requests:
            if not isinstance(request, dict):
                continue
            result = request.get("result", {})
            if not isinstance(result, dict):
                result = {}
            writer.writerow(
                {
                    "Model": result.get("resolvedModel", request.get("modelId", "")),
                    "Prompt": request_text(request),
                    "Credit": summary_credit(request),
                    "Date": display_date(result.get("responseTimestamp", request.get("timestamp"))),
                }
            )

    return len(requests)


def convert(input_path: Path, output_path: Path) -> int:
    requests = load_requests(input_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=[
                "request_id",
                "user_message",
                "response",
                "cache_key",
                "prompt_tokens",
                "output_tokens",
                "completion_tokens",
                "request_timestamp",
                "request_model_id",
                "thinking_tokens",
                "thinking_token_values",
            ],
        )
        writer.writeheader()
        for request in requests:
            if not isinstance(request, dict):
                continue
            row = {
                "request_id": request.get("requestId", ""),
                "user_message": request_text(request),
                "response": response_text(request),
            }
            row.update(metadata_values(request))
            writer.writerow(row)

    return len(requests)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to the chat JSON export")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=None,
        help="Output directory for a timestamped chat.csv, or an explicit CSV file path",
    )
    args = parser.parse_args()

    output_argument = args.output
    if output_argument is None:
        output_argument = (args.input if args.input.is_dir() else args.input.parent) / "csv"

    input_paths = (
        sorted(
            path
            for path in args.input.rglob("*")
            if path.is_file() and path.suffix.lower() in {".json", ".jsonl"}
        )
        if args.input.is_dir()
        else [args.input]
    )
    if not input_paths:
        parser.error(f"No JSON files found in input directory: {args.input}")
    if len(input_paths) > 1 and output_argument.suffix.lower() == ".csv":
        parser.error("An output directory is required when processing multiple JSON files")

    try:
        for input_path in input_paths:
            load_requests(input_path)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(f"Invalid chat export: {error}")

    output_directory = (
        timestamped_output_path(output_argument).parent
        if output_argument.suffix.lower() != ".csv"
        else output_argument.parent
    )
    for input_path in input_paths:
        output_path = (
            output_argument
            if len(input_paths) == 1 and output_argument.suffix.lower() == ".csv"
            else output_directory / f"{input_path.stem}.csv"
        )
        count = convert(input_path, output_path)
        summary_path = output_path.with_name(f"{output_path.stem}_summary.csv")
        write_summary(input_path, summary_path)
        print(f"Wrote {count} request(s) from {input_path} to {output_path}")
        print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
