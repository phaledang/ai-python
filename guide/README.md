# Search in workspace folders
$env:APPDATA\Code\User\workspaceStorage\

$env:APPDATA\Code\User\globalStorage\github.copilot-chat

E.g: $env:APPDATA\Code\User\workspaceStorage\
# Export chat.json
Built-in Export via Command Palette

Step 1 – Open the Chat Session Navigate to the Chat view in VS Code and select the session you want to export.

Step 2 – Run the Export Command Press Ctrl+Shift+P (Windows/Linux) or ⇧⌘P (Mac) to open the Command Palette, then type:

```
Export Chat
```

# Chat Log Conversion

This folder contains the VS Code Copilot export `chat.json` and generated CSV files.

## Copy Copilot transcript JSON files

To copy every GitHub Copilot transcript JSON file from VS Code workspace storage into this folder:

```powershell
Set-Location 'c:\code\..'
.\chatlog\copy-copilot-transcripts.ps1
```

The script searches `$env:APPDATA\Code\User\workspaceStorage\*\GitHub.copilot-chat\transcripts`, including nested folders, and copies both `.json` and `.jsonl` transcript files. Existing files in `chatlog` are skipped and never overwritten. To use another source or destination:

```powershell
.\chatlog\copy-copilot-transcripts.ps1 `
  -WorkspaceStoragePath 'C:\path\to\workspaceStorage' `
  -DestinationPath 'C:\path\to\chatlog'
```

Each run also creates `copy-log-yyyy-MM-dd-HH-mm-ss.csv` in the destination folder. The log contains `SourcePath`, `DestinationPath`, and `Status` columns for every discovered transcript, including files that were skipped because they already existed.

## Run the Python file directly

Open a terminal at the workspace root:

```powershell
Set-Location 'c:\code\..'
python .github\skills\convert-chat-json-to-csv\scripts\convert_chat_json_to_csv.py chatlog\chat.json chatlog\csv
```

The converter creates a new timestamped folder under `chatlog/csv`:

```text
chatlog/csv/yyyy-MM-dd-HH-mm-ss-millisecond/
  chat.csv
  chat_summary.csv
```

`chat.csv` contains the full request and response data, including token and model metadata.

`chat_summary.csv` contains:

```text
Model,Prompt,Credit,Date,WorkspacePath,SessionId
```

`SessionId` is the unique JSONL filename stem for each VS Code chat session, making it possible to group requests from the same session in CSV or Excel.

`Credit` is calculated as:

```text
thinking_tokens + each comma-separated value in thinking_token_values
```

For example:

```text
429 + 21 + 119 + 289 = 858
```

To convert a different input file, replace the input path:

```powershell
python .github\skills\convert-chat-json-to-csv\scripts\convert_chat_json_to_csv.py input.json output-directory
```

An explicit CSV path can also be supplied. In that mode, the timestamped folder is not created:

```powershell
python .github\skills\convert-chat-json-to-csv\scripts\convert_chat_json_to_csv.py input.json output.csv
```

## Extract Copilot workspace summaries

Use `extract_copilot_chat_csv.py` to read Copilot sessions stored by VS Code. The first parameter is the input source. The second parameter is an optional output directory, never an output file. The script creates a timestamped subfolder in the output directory using `yyyy-MM-dd-HH-mm-ss`, then writes `chat_summary.csv` inside it.

Extract one workspace:

```powershell
python .github\skills\github-copilot-chat-csv\scripts\extract_copilot_chat_csv.py `
  "$env:APPDATA\Code\User\workspaceStorage\<workspace-id>" `
  chatlog\csv
```

For example, the output is written to:

```text
chatlog/csv/2026-09-18-14-30-22/chat_summary.csv
```

The workspace must contain `state.vscdb`, `GitHub.copilot-chat`, and sibling `chatSessions` data. The CSV columns are:

```text
Model,Prompt,Credit,Date,WorkspacePath
```

Extract current-month prompts from all eligible workspaces in one run. The script selects workspace folders containing `state.vscdb` and either `GitHub.copilot-chat` or `chatSessions`, filters by each prompt's stored request date, then combines their records:

```powershell
Set-Location 'c:\code\..'
python .github\skills\github-copilot-chat-csv\scripts\extract_copilot_chat_csv.py `
  "$env:APPDATA\Code\User\workspaceStorage"
```

The same timestamped output folder contains `chat_summary.xlsx` and `chat_summary_sort.xlsx`, which store `Credit` as numeric Excel cells; the latter is sorted by date ascending. It also contains `summary_by_session.csv` and `summary_by_session.xlsx`; these keep the first prompt for each `SessionId` and sum all credits from that session into one row with the columns `Model,Prompt,Credit,Date,WorkspacePath,SessionId`. It also contains `credit_totals_by_model.csv`, `credit_totals_by_date.csv`, and `credit_totals_by_model_date.csv`; the last file shows credit for each model on each calendar day. Reconciliation files include `reconciliation_report.json` for category counts and credit totals, `reconciliation_records.jsonl` for source file, record index, and JSON-key provenance, and `reconciliation_records.csv` for spreadsheet analysis. The report distinguishes all raw database credits from current-month credits and flags duplicate candidates.

To choose an explicit output directory:

```powershell
python .github\skills\github-copilot-chat-csv\scripts\extract_copilot_chat_csv.py `
  "$env:APPDATA\Code\User\workspaceStorage" `
  chatlog\csv
```

## Use the skill in Copilot Chat

The workspace skill is located at:

```text
.github/skills/convert-chat-json-to-csv/SKILL.md
```

In Copilot Chat, ask for example:

```text
Convert chatlog/chat.json to CSV and put the output under chatlog/csv.
```

The skill will use the bundled converter and create both CSV files in a new timestamped folder. You can also be explicit:

```text
Use the convert-chat-json-to-csv skill to convert chatlog/chat.json.
Create chat.csv and chat_summary.csv under chatlog/csv, and verify the credit calculations.
```

After conversion, open the newest folder under `chatlog/csv` to view the generated files.
