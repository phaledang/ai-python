---
name: convert-chat-json-to-csv
description: Convert VS Code Copilot chat JSON exports, especially chatlog/chat.json, into a readable CSV file with one row per request. Use when the user asks to convert chat.json or a Copilot conversation export to CSV.
---

# Convert Chat JSON to CSV

Use the bundled `scripts/convert_chat_json_to_csv.py` script to convert a VS Code Copilot chat export into CSV. The input may be an attached JSON/JSONL file, a path supplied by the user, or a directory containing JSON/JSONL files.

Choose the input in this order:

1. Use the path of an attached `.json` file when one is available.
2. Otherwise use the JSON path supplied by the user.
3. For the default workspace workflow, use `chatlog/chat.json`.

## Default workflow

From the workspace root:

```powershell
python .github/skills/convert-chat-json-to-csv/scripts/convert_chat_json_to_csv.py chatlog/chat.json chatlog/csv
```

For an attached or user-supplied input, pass its path and the output directory explicitly:

```powershell
python .github/skills/convert-chat-json-to-csv/scripts/convert_chat_json_to_csv.py input.json output-directory
```

If the output argument is omitted, output is written to `csv/yyyy-MM-dd-HH-mm-ss-millisecond` beside the input file or inside the input directory. For example:

```powershell
python .github/skills/convert-chat-json-to-csv/scripts/convert_chat_json_to_csv.py chatlog/chat.json
python .github/skills/convert-chat-json-to-csv/scripts/convert_chat_json_to_csv.py chatlog
```

For an attached file, substitute its actual attachment path for `input.json`:

```powershell
python .github/skills/convert-chat-json-to-csv/scripts/convert_chat_json_to_csv.py "path/to/attached-chat.json" chatlog/csv
```

The output directory receives a subfolder named `yyyy-MM-dd-HH-mm-ss-millisecond`, containing `chat.csv` and `chat_summary.csv`. An explicit `.csv` output path is also supported when a timestamped folder is not wanted.

When the input is a directory, all `.json` and `.jsonl` files in it and its subdirectories are validated first. JSONL files may contain one request object per non-empty line or Copilot event records. Event records are grouped into one main CSV row per `user.message`, with subsequent assistant message content collected into the response; their summary CSV contains only `assistant.message` events. Each file is then converted into the output directory using its input filename, such as `conversation.csv` and `conversation_summary.csv`. Use an output directory rather than an explicit `.csv` path for this mode.

The converter:

- Writes one row for each item in the top-level `requests` array.
- Preserves the request ID.
- Extracts the user text from `message.text`, including text assembled from `message.parts` when needed.
- Flattens response text and common response message fields into a single response column.
- Includes cache key, prompt/output/completion token counts, request timestamp and model ID.
- Includes total thinking tokens and the individual thinking-token values from tool-call rounds.
- Also writes `chat_summary.csv` with `Model`, `Prompt`, `Credit`, and `Date` columns. `Credit` is calculated as `thinking_tokens` plus the sum of every comma-separated value in `thinking_token_values`.
- Uses UTF-8 CSV with a header row and safe CSV quoting.
- Does not modify the source JSON.

After running it, report the output path and the number of rows written. If the input is not a VS Code chat export, inspect its top-level structure and adapt the extraction rather than silently producing an empty CSV.
