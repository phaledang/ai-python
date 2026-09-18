---
name: github-copilot-chat-csv
description: Extract, clean, summarize, or filter GitHub Copilot Chat CSV exports that contain Model, Prompt, Credit, and Date columns. Use when a user provides a Copilot Chat export and wants its chat metadata or prompts analyzed.
---

# Github Copilot Chat Csv

Use this skill for Copilot Chat data whose expected columns are `Model`, `Prompt`, `Credit`, and `Date`.
The source may be an exported CSV, a SQLite database, or a VS Code workspace-storage folder such as `$env:APPDATA/Code/User/workspaceStorage/<workspace-id>/GitHub.copilot-chat`.

1. Inspect the CSV header before making claims. Accept a UTF-8 BOM and normalize surrounding whitespace in header names.
2. Preserve each original row and normalize it to these fields: `model`, `prompt`, `credit`, and `date`. Treat blank values as null; do not invent missing values.
3. Parse dates only when the format is unambiguous. Keep the original date string alongside a parsed value if analysis needs chronological sorting.
4. Report malformed rows, missing required columns, and duplicate records separately rather than silently dropping them.
5. By default, produce a concise summary: record count, date range, model usage, total/available credit information, and recurring prompt themes. Include full prompt text only when the user asks for it, because exports can contain sensitive project details.
6. When the user wants reusable data, create a normalized JSON or CSV output and retain the source-row number for traceability.

Run `scripts/extract_copilot_chat_csv.py` to create a timestamped summary CSV. The optional second argument is an output directory, never an output file. If omitted, the default is `chatlog/csv`:

```powershell
python scripts/extract_copilot_chat_csv.py "C:\Users\<user>\AppData\Roaming\Code\User\workspaceStorage\<workspace-id>\GitHub.copilot-chat"
```

The script recursively discovers `.db`, `.sqlite`, and `.sqlite3` files and reads the first table containing all four required columns. For a VS Code workspace-storage folder, it also reads sibling `chatSessions/*.jsonl` files indexed by `state.vscdb`; these contain the initial request snapshot, appended request events, and credit patches. In that source, `Credit` is the stored `copilotCredits` value for the prompt. If VS Code did not persist `copilotCredits`, the field remains blank rather than being changed to zero. The optional second argument is always an output directory, never a CSV filename:

```powershell
python scripts/extract_copilot_chat_csv.py "C:\Users\<user>\AppData\Roaming\Code\User\workspaceStorage\<workspace-id>\GitHub.copilot-chat" chatlog\csv
```

Prompt text is normalized for CSV readability: non-ASCII and control characters are removed, whitespace is collapsed, and the result is limited to 500 characters.

Summary CSV output also includes `WorkspacePath` and `SessionId`. For VS Code `chatSessions/*.jsonl` input, `SessionId` is the unique JSONL filename stem for the chat session; non-session inputs leave it blank rather than inventing an identifier.

This CSV is a local workspace-session extract, not an account billing report. Its numeric credits cannot be compared directly with the monthly usage meter shown in GitHub Copilot. The monthly meter may include other devices, web or CLI usage, inline completions, and server-side usage that is absent from local workspace storage.

Each run creates `chatlog/csv/<yyyy-MM-dd-HH-mm-ss>/chat_summary.csv`. A workspace folder with no `chatSessions/*.jsonl` snapshots cannot produce a summary.

Each run also creates `chat_summary.xlsx`, `chat_summary_sort.xlsx`, `summary_by_session.csv`, and `summary_by_session.xlsx`, plus `credit_totals_by_model.csv`, `credit_totals_by_date.csv`, `credit_totals_by_model_date.csv`, `reconciliation_report.json`, `reconciliation_records.jsonl`, and `reconciliation_records.csv` beside `chat_summary.csv`. Both Excel files write `Credit` as numeric cells for reliable spreadsheet totals; `chat_summary_sort.xlsx` is explicitly sorted by date ascending. The session summaries keep the first prompt for each `SessionId` and sum all credits from that session into one row, using the six columns `Model,Prompt,Credit,Date,WorkspacePath,SessionId`. The model/date CSVs contain record counts and six-decimal credit totals for included current-month records; `credit_totals_by_model_date.csv` contains one row per model per calendar day. The report classifies raw records as included current-month chat, missing prompt, missing date/model, missing credit, or other-date Copilot usage. It includes all-record and current-month raw credit totals, duplicate candidates, SessionId, and source JSON keys/record indexes for tracing individual records.

To extract the current calendar month from every workspace, pass the parent `workspaceStorage` folder instead. The script selects workspace IDs containing `state.vscdb` and either `GitHub.copilot-chat` or `chatSessions`, reads their `chatSessions/*.jsonl` files, filters requests by their stored request date, and combines the results into one timestamped project output. Workspace folder creation dates are not used as the activity filter because older workspaces can contain current-month prompts:

```powershell
python scripts/extract_copilot_chat_csv.py "$env:APPDATA\Code\User\workspaceStorage"
```
