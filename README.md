# Relay

A provider-agnostic, local-first, BYOK AI coding agent for your terminal.

Relay understands existing codebases, plans and executes engineering tasks, runs tools and tests under strict permission boundaries, renders live Markdown responses, and persists sessions locally in SQLite.

---

## Key Features

- **Provider-Agnostic & BYOK:** Supports **OpenRouter**, **Groq**, **Anthropic Claude**, **OpenAI**, **Google Gemini**, and local **Ollama** models behind a single normalized interface.
- **Interactive Onboarding & Dark Terminal UI:** Launching `relay` opens an animated dark interface with a provider selection dropdown, masked OS-keyring API key prompt, model input box, live thinking/tool spinners, and real-time Markdown streaming.
- **Mid-Session Model Switching (`/model`):** Switch providers, API keys, or models seamlessly mid-conversation with automatic SQLite session updates.
- **Local-First & Private:** Source files, command execution, SQLite history, and OS keyring credentials remain strictly on your local machine.
- **Robust Security & Permissions:** 4 permission modes (`plan`, `ask`, `auto-edit`, `full-auto`), path-traversal protection, lexical command risk classification, and pre-write snapshots with unified diffs.
- **Autonomous Agent Runtime & Workflows:** Streaming turn loop with token budgeting, transcript compaction, retries with exponential backoff, and LangGraph plan/review/repair workflows.
- **Extensible:** Model Context Protocol (MCP) stdio client, `.agents/skills` discovery, and configurable lifecycle hooks.

---

## Installation & Setup

### Requirements
- Python 3.11 or newer
- Git

### Install via pip (editable)
```bash
git clone <your-repo-url>
cd Relay
python -m venv .venv

# Windows (PowerShell): .\.venv\Scripts\Activate.ps1
# Windows (Git Bash):   source .venv/Scripts/activate
# macOS / Linux:        source .venv/bin/activate

pip install -e ".[dev]"
```

### Verify Environment
Run diagnostics to verify Python version, OS keyring availability, Git, Ripgrep, and SQLite migrations:
```bash
relay doctor
```

---

## Quick Start

### 1. Launch Interactive Session (Recommended)
Simply run `relay` in any repository directory:
```bash
relay
```
Relay launches a guided startup flow:
1. **Provider Dropdown:** Choose from OpenRouter, Groq, Anthropic, OpenAI, Google Gemini, or Ollama using `↑`/`↓` or number keys `1–6`.
2. **API Key Box:** Paste your API key (saved securely in your OS keyring; press `Enter` on future launches to reuse your saved key, or skip for local Ollama).
3. **Model Name Box:** Enter the model ID you want to use.

You can bypass the startup flow anytime with CLI flags:
```bash
relay --provider openai --model gpt-4o
relay --debug   # Enable verbose HTTP and diagnostic logging
```

### 2. Interactive Slash Commands
Inside an interactive `relay` session:
- `/help` — Show all interactive commands
- `/model` — Switch provider, API key, or model mid-session (also supports `/model <model>`, `/model <provider>`, or `/model <provider> <model>`)
- `/diff` — Show working tree unified git diff
- `/status` — Show active provider, model, permission mode, modified files, and token usage
- `/permissions [mode]` — Inspect or switch permission mode (`plan`, `ask`, `auto-edit`, `full-auto`)
- `/sessions` — List recent sessions for the current workspace
- `/export [format]` — Export the session transcript (`markdown` or `json`)
- `/clear` — Clear the terminal screen
- `/quit` — Exit the interactive session

### 3. Pre-Configure Providers via CLI
You can also configure or test providers directly from the command line:
```bash
relay provider add openrouter --model <MODEL_ID> --api-key <YOUR_KEY>
relay provider add groq --model <MODEL_ID> --api-key <YOUR_KEY>
relay provider add anthropic --model <MODEL_ID> --api-key <YOUR_KEY>
relay provider add openai --model <MODEL_ID> --api-key <YOUR_KEY>
relay provider add gemini --model <MODEL_ID> --api-key <YOUR_KEY>
relay provider add ollama --model <MODEL_ID>

relay provider list
relay provider test <provider>
```

### 4. Workspace & Non-Interactive Tasks
```bash
# Generate .relay/ and AGENTS.md template
relay init

# Autonomous single-shot execution
relay ask "Find all unused imports in the codebase and remove them"

# Read-only analysis and planning
relay plan "Refactor session database queries"
```

---

## Configuration & Security

Relay resolves configuration in strict precedence order:
1. CLI flags (`--provider`, `--model`, `--api-key`, `--workspace`, `--debug`)
2. Environment variables (`OPENROUTER_API_KEY`, `GROQ_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `RELAY_DEFAULT_PROVIDER`, `RELAY_PERMISSION_MODE`)
3. Workspace config (`.relay/config.toml` or `relay.toml`)
4. Global user config (`~/.config/relay/config.toml`)
5. Application defaults

### Permission Modes
- **`plan`**: Read-only exploration. No file writes or state-changing commands permitted.
- **`ask`** (Default): Read operations run automatically; file writes and shell commands prompt for approval.
- **`auto-edit`**: In-workspace file edits are allowed automatically; terminal commands and out-of-workspace access prompt for approval.
- **`full-auto`**: Opt-in autonomous workflow mode scoped to the workspace; destructive commands remain gated.

---

## Architecture & Testing

See [Relay/ARCHITECTURE.md](ARCHITECTURE.md) for system diagrams, module contracts, SQLite schema, and security boundaries.

Run the automated test suite with pytest:
```bash
pytest
```
